from __future__ import annotations

import asyncio
import logging

from nq_atlas.flow import FlowEngine
from nq_atlas.gex import GEXEngine
from nq_atlas.nq_mapper import map_chain_levels
from nq_atlas.server import broadcast_state
from nq_atlas.state import AtlasState
from nq_atlas.vanna_charm import VannaCharmEngine

logger = logging.getLogger(__name__)

gex_engine = GEXEngine()
vanna_engine = VannaCharmEngine()


async def compute_loop(state: AtlasState, flow_engine: FlowEngine) -> None:
    """Runs GEX → vanna/charm → flow → NQ mapper on each new chain snapshot."""
    last_chain_ts = None

    while True:
        await asyncio.sleep(0.5)

        if state.chain is None or state.last_chain_ts == last_chain_ts:
            continue

        last_chain_ts = state.last_chain_ts
        chain = state.chain
        qqq_spot = state.spots.get("QQQ", chain.spot_price)
        nq_spot = state.spots.get("NQ", 0.0)

        try:
            state.gex = gex_engine.compute(chain)
            state.vanna_charm = vanna_engine.compute(chain)

            for contract in chain.contracts:
                if contract.last is not None and contract.volume:
                    flow_engine.update(
                        {
                            "price": contract.last,
                            "bid": contract.bid or 0,
                            "ask": contract.ask or 0,
                            "volume": contract.volume,
                            "call_put": contract.call_put,
                        }
                    )
            state.flow = flow_engine.compute()

            if nq_spot > 0 and qqq_spot > 0:
                state.nq_levels = map_chain_levels(state.gex, qqq_spot, nq_spot)

            await broadcast_state(state.snapshot_dict())

            logger.info(
                "compute: GEX regime=%+d vanna_dir=%+d flow_dir=%+d",
                state.gex.regime_sign,
                state.vanna_charm.dealer_hedge_direction if state.vanna_charm else 0,
                state.flow.net_direction if state.flow else 0,
            )
        except Exception as e:
            logger.error("compute_loop error: %s", e)
            state.log_error("compute_loop", str(e))


__all__ = ["compute_loop"]
