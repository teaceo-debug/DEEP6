"""Session state persistence tests — SQLite via aiosqlite."""
import pytest
import pytest_asyncio
import time
from deep6.state.persistence import SessionPersistence


@pytest.fixture
async def persistence(tmp_path):
    db_path = str(tmp_path / "test.db")
    p = SessionPersistence(db_path)
    await p.initialize()
    return p


@pytest.mark.asyncio
async def test_read_all_empty(persistence):
    result = await persistence.read_all("session_20260411")
    assert result == {}


@pytest.mark.asyncio
async def test_write_and_read(persistence):
    await persistence.write("session_20260411", "cvd", "42")
    result = await persistence.read_all("session_20260411")
    assert result["cvd"] == "42"


@pytest.mark.asyncio
async def test_write_update_existing(persistence):
    await persistence.write("session_20260411", "cvd", "10")
    await persistence.write("session_20260411", "cvd", "99")
    result = await persistence.read_all("session_20260411")
    assert result["cvd"] == "99"


@pytest.mark.asyncio
async def test_multiple_keys(persistence):
    await persistence.write("s1", "cvd", "100")
    await persistence.write("s1", "vwap_numerator", "21000.5")
    result = await persistence.read_all("s1")
    assert result["cvd"] == "100"
    assert result["vwap_numerator"] == "21000.5"


@pytest.mark.asyncio
async def test_session_isolation(persistence):
    """Different session_ids do not interfere."""
    await persistence.write("session_a", "cvd", "10")
    await persistence.write("session_b", "cvd", "20")
    a = await persistence.read_all("session_a")
    b = await persistence.read_all("session_b")
    assert a["cvd"] == "10"
    assert b["cvd"] == "20"


@pytest.mark.asyncio
async def test_persist_session_context(persistence):
    """Full round-trip: SessionContext -> write -> read -> SessionContext."""
    from deep6.state.session import SessionContext
    ctx = SessionContext()
    ctx.cvd = 333
    ctx.vwap_numerator = 21000.5 * 1000
    ctx.vwap_denominator = 1000.0
    ctx.ib_high = 21100.0
    ctx.ib_low = 21000.0
    ctx.ib_complete = True

    sid = "session_20260411"
    for k, v in ctx.to_dict().items():
        await persistence.write(sid, k, v)

    restored = SessionContext.from_dict(await persistence.read_all(sid))
    assert restored.cvd == 333
    assert restored.ib_complete is True
    assert abs(restored.vwap_numerator - 21000.5 * 1000) < 0.01
