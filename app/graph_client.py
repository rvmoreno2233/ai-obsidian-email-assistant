"""Microsoft Graph email backend with MSAL auth and mock implementation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

import msal

from app.config import (
    FIXTURES_DIR,
    MSAL_CACHE_PATH,
    MSGRAPH_CLIENT_ID,
    MSGRAPH_SCOPES,
    MSGRAPH_TENANT_ID,
)
from app.schemas import NormalizedEmail
from app.text_utils import normalize_body


@runtime_checkable
class EmailBackend(Protocol):
    """Interface for email read/write operations."""

    def list_recent_messages(self, top: int = 25) -> list[NormalizedEmail]: ...

    def get_message_body(self, message_id: str) -> str: ...

    def create_reply_draft(
        self,
        message_id: str,
        subject: str,
        body: str,
    ) -> str | None: ...

    def mark_as_read(self, message_id: str) -> None: ...

    def add_category(self, message_id: str, category: str) -> None: ...


class MockGraphBackend:
    """Reads sample emails from fixtures for offline development."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or FIXTURES_DIR / "sample_emails.json"
        self._drafts: dict[str, dict] = {}

    def list_recent_messages(self, top: int = 25) -> list[NormalizedEmail]:
        if not self.fixture_path.exists():
            return []
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        emails = [NormalizedEmail.model_validate(e) for e in raw]
        return emails[:top]

    def get_message_body(self, message_id: str) -> str:
        for email in self.list_recent_messages(top=1000):
            if email.message_id == message_id:
                return email.body_text
        return ""

    def create_reply_draft(
        self,
        message_id: str,
        subject: str,
        body: str,
    ) -> str | None:
        draft_id = f"draft-{message_id}"
        self._drafts[draft_id] = {
            "message_id": message_id,
            "subject": subject,
            "body": body,
        }
        return draft_id

    def mark_as_read(self, message_id: str) -> None:
        pass

    def add_category(self, message_id: str, category: str) -> None:
        pass

    def list_messages_for_sender(self, sender_email: str, top: int = 5) -> list[NormalizedEmail]:
        needle = sender_email.lower().strip()
        results: list[NormalizedEmail] = []
        for email in self.list_recent_messages(top=1000):
            if email.sender_email.lower() == needle:
                results.append(email)
            if len(results) >= top:
                break
        return results


def _build_msal_app() -> msal.PublicClientApplication:
    MSAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = msal.SerializableTokenCache()
    if MSAL_CACHE_PATH.exists():
        cache.deserialize(MSAL_CACHE_PATH.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        MSGRAPH_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{MSGRAPH_TENANT_ID}",
        token_cache=cache,
    )
    app._token_cache = cache  # type: ignore[attr-defined]
    return app


def acquire_token_interactive() -> str:
    """Run device code flow and cache token."""
    if not MSGRAPH_CLIENT_ID:
        raise ValueError("MSGRAPH_CLIENT_ID is required for Graph authentication")

    app = _build_msal_app()
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(MSGRAPH_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _persist_cache(app)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=MSGRAPH_SCOPES)
    if "user_code" not in flow:
        desc = flow.get("error_description", str(flow))
        if "50059" in desc:
            raise RuntimeError(
                f"Device flow failed: {desc}\n"
                "Fix: set MSGRAPH_TENANT_ID to your work tenant ID (not 'common'). "
                "Azure Portal → Microsoft Entra ID → Overview → Tenant ID."
            )
        raise RuntimeError(f"Device flow failed: {flow}")
    print(flow["message"], file=sys.stderr)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "Token acquisition failed"))
    _persist_cache(app)
    return result["access_token"]


def _persist_cache(app: msal.PublicClientApplication) -> None:
    cache = getattr(app, "_token_cache", None)
    if cache and cache.has_state_changed:
        MSAL_CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")


class MsGraphBackend:
    """Microsoft Graph implementation using msgraph-sdk (sync wrapper)."""

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token
        self._client = None

    def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        return acquire_token_interactive()

    def _get_client(self):
        if self._client is not None:
            return self._client

        from azure.core.credentials import AccessToken, TokenCredential
        from msgraph import GraphServiceClient

        token = self._get_token()

        class StaticTokenCredential(TokenCredential):
            def get_token(self, *scopes, **kwargs):
                return AccessToken(token, 9999999999)

            async def get_token_async(self, *scopes, **kwargs):
                return AccessToken(token, 9999999999)

        self._client = GraphServiceClient(credentials=StaticTokenCredential())
        return self._client

    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)

    def list_recent_messages(self, top: int = 25) -> list[NormalizedEmail]:
        return self._run(self._alist_recent_messages(top))

    async def _alist_recent_messages(self, top: int) -> list[NormalizedEmail]:
        from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (  # noqa: E501
            MessagesRequestBuilder,
        )

        client = self._get_client()
        query = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            select=["id", "subject", "from", "body", "receivedDateTime", "webLink", "isRead"],
            top=top,
            orderby=["receivedDateTime DESC"],
        )
        config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
            query_parameters=query,
        )
        page = await client.me.mail_folders.by_mail_folder_id("inbox").messages.get(
            request_configuration=config,
        )
        results: list[NormalizedEmail] = []
        if page and page.value:
            for msg in page.value:
                sender = msg.from_
                sender_email = ""
                sender_name = None
                if sender and sender.email_address:
                    sender_email = sender.email_address.address or ""
                    sender_name = sender.email_address.name
                body_text = ""
                if msg.body and msg.body.content:
                    body_text = normalize_body(msg.body.content)
                results.append(
                    NormalizedEmail(
                        message_id=msg.id or "",
                        subject=msg.subject or "",
                        sender_name=sender_name,
                        sender_email=sender_email,
                        received_at=str(msg.received_date_time or ""),
                        body_text=body_text,
                        web_link=msg.web_link,
                    )
                )
        return results

    def list_messages_metadata(
        self,
        folder: str = "inbox",
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list:
        """Paginate inbox metadata (no body) for catalog scraping."""
        return self._run(self._alist_messages_metadata(folder, page_size, max_pages))

    async def _alist_messages_metadata(self, folder: str, page_size: int, max_pages: int) -> list:
        from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (  # noqa: E501
            MessagesRequestBuilder,
        )

        from app.inbox_catalog import MessageMeta

        client = self._get_client()
        query = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            select=["id", "subject", "from", "receivedDateTime", "bodyPreview"],
            top=min(page_size, 100),
            orderby=["receivedDateTime DESC"],
        )
        config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
            query_parameters=query,
        )
        request = client.me.mail_folders.by_mail_folder_id(folder).messages
        page = await request.get(request_configuration=config)
        results: list[MessageMeta] = []
        pages = 0

        while page and pages < max_pages:
            pages += 1
            if page.value:
                for msg in page.value:
                    sender = msg.from_
                    sender_email = ""
                    sender_name = None
                    if sender and sender.email_address:
                        sender_email = sender.email_address.address or ""
                        sender_name = sender.email_address.name
                    results.append(
                        MessageMeta(
                            message_id=msg.id or "",
                            subject=msg.subject or "",
                            sender_email=sender_email,
                            sender_name=sender_name,
                            received_at=str(msg.received_date_time or ""),
                            body_preview=getattr(msg, "body_preview", None) or "",
                        )
                    )
            if not page.odata_next_link:
                break
            page = await request.with_url(page.odata_next_link).get(
                request_configuration=config,
            )
            if pages % 10 == 0:
                print(f"  ... scraped {len(results)} messages ({pages} pages)", flush=True)

        return results

    def list_messages_for_domain(self, domain: str, top: int = 5) -> list[NormalizedEmail]:
        """Fetch recent inbox messages from a sender domain."""
        return self._run(self._alist_messages_for_domain(domain, top))

    def list_messages_for_sender(self, sender_email: str, top: int = 5) -> list[NormalizedEmail]:
        """Fetch recent inbox messages from a specific sender."""
        return self._run(self._alist_messages_for_sender(sender_email, top))

    async def _alist_messages_for_domain(self, domain: str, top: int) -> list[NormalizedEmail]:
        from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (  # noqa: E501
            MessagesRequestBuilder,
        )

        client = self._get_client()
        needle = f"@{domain.lower()}"
        query = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            select=["id", "subject", "from", "body", "bodyPreview", "receivedDateTime", "webLink"],
            top=min(top * 4, 50),
            orderby=["receivedDateTime DESC"],
            filter=f"contains(from/emailAddress/address,'{needle}')",
        )
        config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
            query_parameters=query,
        )
        page = await client.me.mail_folders.by_mail_folder_id("inbox").messages.get(
            request_configuration=config,
        )
        results: list[NormalizedEmail] = []
        if page and page.value:
            for msg in page.value:
                sender = msg.from_
                sender_email = ""
                sender_name = None
                if sender and sender.email_address:
                    sender_email = sender.email_address.address or ""
                    sender_name = sender.email_address.name
                if not sender_email.lower().endswith(needle):
                    continue
                preview = getattr(msg, "body_preview", None) or ""
                body_text = preview
                if msg.body and msg.body.content and not preview:
                    body_text = normalize_body(msg.body.content)[:500]
                elif msg.body and msg.body.content:
                    body_text = preview or normalize_body(msg.body.content)[:500]
                results.append(
                    NormalizedEmail(
                        message_id=msg.id or "",
                        subject=msg.subject or "",
                        sender_name=sender_name,
                        sender_email=sender_email,
                        received_at=str(msg.received_date_time or ""),
                        body_text=body_text,
                        web_link=msg.web_link,
                    )
                )
                if len(results) >= top:
                    break
        return results

    async def _alist_messages_for_sender(
        self, sender_email: str, top: int
    ) -> list[NormalizedEmail]:
        from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (  # noqa: E501
            MessagesRequestBuilder,
        )

        client = self._get_client()
        needle = sender_email.lower().strip()
        query = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            select=["id", "subject", "from", "body", "bodyPreview", "receivedDateTime", "webLink"],
            top=min(top * 4, 50),
            orderby=["receivedDateTime DESC"],
            filter=f"contains(from/emailAddress/address,'{needle}')",
        )
        config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
            query_parameters=query,
        )
        page = await client.me.mail_folders.by_mail_folder_id("inbox").messages.get(
            request_configuration=config,
        )
        results: list[NormalizedEmail] = []
        if page and page.value:
            for msg in page.value:
                sender = msg.from_
                sender_email_addr = ""
                sender_name = None
                if sender and sender.email_address:
                    sender_email_addr = sender.email_address.address or ""
                    sender_name = sender.email_address.name
                if sender_email_addr.lower() != needle:
                    continue
                preview = getattr(msg, "body_preview", None) or ""
                body_text = preview
                if msg.body and msg.body.content and not preview:
                    body_text = normalize_body(msg.body.content)[:500]
                elif msg.body and msg.body.content:
                    body_text = preview or normalize_body(msg.body.content)[:500]
                results.append(
                    NormalizedEmail(
                        message_id=msg.id or "",
                        subject=msg.subject or "",
                        sender_name=sender_name,
                        sender_email=sender_email_addr,
                        received_at=str(msg.received_date_time or ""),
                        body_text=body_text,
                        web_link=msg.web_link,
                    )
                )
                if len(results) >= top:
                    break
        return results

    def get_message_preview(self, message_id: str) -> dict:
        """Full message preview for UI."""
        return self._run(self._aget_message_preview(message_id))

    async def _aget_message_preview(self, message_id: str) -> dict:
        client = self._get_client()
        msg = await client.me.messages.by_message_id(message_id).get()
        if not msg:
            return {}
        sender = msg.from_
        sender_email = ""
        sender_name = None
        if sender and sender.email_address:
            sender_email = sender.email_address.address or ""
            sender_name = sender.email_address.name
        body = ""
        if msg.body and msg.body.content:
            body = normalize_body(msg.body.content)
        preview = getattr(msg, "body_preview", None) or body[:500]
        return {
            "message_id": msg.id or message_id,
            "subject": msg.subject or "",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "received_at": str(msg.received_date_time or ""),
            "body_preview": preview,
            "body_text": body[:4000],
            "web_link": msg.web_link,
        }

    def get_message_body(self, message_id: str) -> str:
        return self._run(self._aget_message_body(message_id))

    async def _aget_message_body(self, message_id: str) -> str:
        client = self._get_client()
        msg = await client.me.messages.by_message_id(message_id).get()
        if msg and msg.body and msg.body.content:
            return msg.body.content
        return ""

    def create_reply_draft(
        self,
        message_id: str,
        subject: str,
        body: str,
    ) -> str | None:
        return self._run(self._acreate_reply_draft(message_id, subject, body))

    async def _acreate_reply_draft(self, message_id: str, subject: str, body: str) -> str | None:
        from msgraph.generated.models.body_type import BodyType
        from msgraph.generated.models.item_body import ItemBody
        from msgraph.generated.models.message import Message
        from msgraph.generated.users.item.messages.item.create_reply.create_reply_post_request_body import (  # noqa: E501
            CreateReplyPostRequestBody,
        )

        client = self._get_client()
        reply_body = CreateReplyPostRequestBody()
        draft = await client.me.messages.by_message_id(message_id).create_reply.post(reply_body)
        if draft and draft.id:
            update = Message()
            update.subject = subject
            update.body = ItemBody()
            update.body.content_type = BodyType.Text
            update.body.content = body
            await client.me.messages.by_message_id(draft.id).patch(update)
            return draft.id
        return None

    def mark_as_read(self, message_id: str) -> None:
        self._run(self._amark_as_read(message_id))

    async def _amark_as_read(self, message_id: str) -> None:
        from msgraph.generated.models.message import Message

        client = self._get_client()
        update = Message()
        update.is_read = True
        await client.me.messages.by_message_id(message_id).patch(update)

    def add_category(self, message_id: str, category: str) -> None:
        self._run(self._aadd_category(message_id, category))

    async def _aadd_category(self, message_id: str, category: str) -> None:
        from msgraph.generated.models.message import Message

        client = self._get_client()
        msg = await client.me.messages.by_message_id(message_id).get()
        categories = list(msg.categories or []) if msg else []
        if category not in categories:
            categories.append(category)
        update = Message()
        update.categories = categories
        await client.me.messages.by_message_id(message_id).patch(update)


def get_email_backend(backend_name: str | None = None) -> EmailBackend:
    from app.config import EMAIL_BACKEND

    name = (backend_name or EMAIL_BACKEND).lower()
    if name == "graph":
        return MsGraphBackend()
    return MockGraphBackend()
