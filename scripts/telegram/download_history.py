"""Download full message history from MAD Levels Telegram channels (NQ + ES).

Usage:
    python scripts/telegram/download_history.py

First run: prompts for phone number + code (Telegram auth).
Subsequent runs: reuses saved session (deep6_telegram.session).

Output:
    data/telegram_levels/raw_nq.json   — all NQ channel messages
    data/telegram_levels/raw_es.json   — all ES channel messages

Each message is stored as:
    {
        "message_id": int,
        "date": "ISO 8601 UTC",
        "edit_date": "ISO 8601 UTC" or null,
        "sender_id": int or null,
        "text": str or null,
        "media_type": str or null,
        "reply_to": int or null,
        "forwarded": bool
    }
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)

# ── Config ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_FILE = str(SCRIPT_DIR / "deep6_telegram")

# Channel invite hashes (from t.me/+HASH links)
NQ_CHANNEL_HASH = "J4WHzA8EE5E2N2Nl"
ES_CHANNEL_HASH = "mAiBHnFQ3gA4YjA1"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "telegram_levels"


def _media_type(msg) -> str | None:
    """Classify message media type."""
    if msg.media is None:
        return None
    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"
    if isinstance(msg.media, MessageMediaDocument):
        return "document"
    if isinstance(msg.media, MessageMediaWebPage):
        return "webpage"
    return type(msg.media).__name__


def _serialize_msg(msg) -> dict:
    """Convert a Telethon Message to a JSON-serializable dict."""
    return {
        "message_id": msg.id,
        "date": msg.date.astimezone(timezone.utc).isoformat() if msg.date else None,
        "edit_date": (
            msg.edit_date.astimezone(timezone.utc).isoformat()
            if msg.edit_date
            else None
        ),
        "sender_id": msg.sender_id,
        "text": msg.text or None,
        "media_type": _media_type(msg),
        "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        "forwarded": msg.forward is not None,
    }


async def _join_channel(client: TelegramClient, invite_hash: str):
    """Join a channel via invite hash if not already a member."""
    from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
    from telethon.errors import UserAlreadyParticipantError, InviteHashExpiredError

    try:
        result = await client(CheckChatInviteRequest(invite_hash))
        # If we get ChatInviteAlready, we're already in
        from telethon.tl.types import ChatInviteAlready
        if isinstance(result, ChatInviteAlready):
            print(f"  Already a member of channel (hash={invite_hash[:8]}...)")
            return result.chat
        else:
            print(f"  Joining channel (hash={invite_hash[:8]}...)...")
            updates = await client(ImportChatInviteRequest(invite_hash))
            return updates.chats[0] if updates.chats else None
    except UserAlreadyParticipantError:
        print(f"  Already a member of channel (hash={invite_hash[:8]}...)")
        # Get the entity through dialogs
        return None
    except InviteHashExpiredError:
        print(f"  ERROR: Invite hash expired for {invite_hash[:8]}...")
        return None


async def _resolve_channel(client: TelegramClient, invite_hash: str):
    """Resolve invite hash to an entity we can iterate messages from."""
    # First try joining (or confirming membership)
    chat = await _join_channel(client, invite_hash)
    if chat is not None:
        return chat

    # Fallback: search through our dialogs
    print(f"  Searching dialogs for channel...")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if hasattr(entity, 'username') and entity.username:
            continue  # skip public channels, we want private ones
        # We'll need to match by checking if this is the right channel
        # Since we can't easily match invite hash to entity, we return all
        # channel-type entities and let the caller verify
    return None


async def _download_channel(
    client: TelegramClient, invite_hash: str, label: str, output_path: Path
) -> int:
    """Download all messages from a channel and save to JSON."""
    print(f"\n{'='*60}")
    print(f"Downloading {label} channel (hash={invite_hash[:8]}...)")
    print(f"{'='*60}")

    # Resolve channel entity
    entity = await _resolve_channel(client, invite_hash)

    if entity is None:
        # Try getting entity directly from invite link
        from telethon.tl.functions.messages import CheckChatInviteRequest
        from telethon.tl.types import ChatInviteAlready
        result = await client(CheckChatInviteRequest(invite_hash))
        if isinstance(result, ChatInviteAlready):
            entity = result.chat
        else:
            print(f"  ERROR: Could not resolve channel. Are you a member?")
            return 0

    print(f"  Channel resolved: {getattr(entity, 'title', 'Unknown')}")
    print(f"  Downloading all messages...")

    messages = []
    count = 0
    async for msg in client.iter_messages(entity, limit=None, wait_time=0.5):
        messages.append(_serialize_msg(msg))
        count += 1
        if count % 500 == 0:
            print(f"    ...{count} messages downloaded")

    # Save newest-first (default from Telethon)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)

    print(f"  DONE: {count} messages saved to {output_path}")

    # Quick stats
    text_count = sum(1 for m in messages if m["text"])
    media_count = sum(1 for m in messages if m["media_type"])
    fwd_count = sum(1 for m in messages if m["forwarded"])
    if messages:
        oldest = messages[-1]["date"]
        newest = messages[0]["date"]
        print(f"  Date range: {oldest} to {newest}")
    print(f"  Text messages: {text_count}")
    print(f"  Media messages: {media_count}")
    print(f"  Forwarded: {fwd_count}")

    return count


async def main():
    print("DEEP6 Telegram History Downloader")
    print("=" * 60)
    print(f"API ID: {API_ID}")
    print(f"Session: {SESSION_FILE}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Accept phone as arg1, verification code as arg2
    phone = sys.argv[1] if len(sys.argv) > 1 else None
    code = sys.argv[2] if len(sys.argv) > 2 else None
    password_2fa = sys.argv[3] if len(sys.argv) > 3 else None

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        if not phone:
            print("ERROR: Not authorized. Pass phone number as first argument.")
            print("Usage: python download_history.py +1XXXXXXXXXX CODE")
            sys.exit(1)

        # Always send code request to get fresh phone_code_hash
        sent = await client.send_code_request(phone)
        phone_code_hash = sent.phone_code_hash

        if not code:
            print("Verification code sent to your Telegram app.")
            print("Re-run with the code as second argument:")
            print(f"  python scripts/telegram/download_history.py {phone} XXXXX")
            await client.disconnect()
            sys.exit(0)

        # Sign in with code + hash
        from telethon.errors import SessionPasswordNeededError
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if password_2fa:
                await client.sign_in(password=password_2fa)
            else:
                print("2FA is enabled. Re-run with your 2FA password as third argument:")
                print(f"  python scripts/telegram/download_history.py {phone} CODE YOUR_PASSWORD")
                await client.disconnect()
                sys.exit(1)

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id})")

    # Download both channels
    nq_count = await _download_channel(
        client, NQ_CHANNEL_HASH, "NQ MAD Levels", OUTPUT_DIR / "raw_nq.json"
    )

    es_count = await _download_channel(
        client, ES_CHANNEL_HASH, "ES MAD Levels", OUTPUT_DIR / "raw_es.json"
    )

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  NQ messages: {nq_count}")
    print(f"  ES messages: {es_count}")
    print(f"  Total: {nq_count + es_count}")
    print(f"  Files: {OUTPUT_DIR / 'raw_nq.json'}")
    print(f"         {OUTPUT_DIR / 'raw_es.json'}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
