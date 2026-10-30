import asyncio
import logging
import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from legacy.config import WEBHOOK_SECRET, PORT
from legacy.agents.cortexkeeper import run_cortexkeeper
from legacy.agents.guardkeeper import run_guardkeeper
from legacy.agents.specforge import run_specforge, run_spec_compliance, handle_spec_approval
from legacy.agents.cortexcast import run_cortexcast
from legacy.agents.onboarding import run_onboarding
from legacy.agents.orgkeeper import run_orgkeeper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("cortex server starting up")
    yield
    logger.info("cortex server shutting down")


app = FastAPI(
    title="cortex — Living Organisational Record Engine",
    description="Multi-agent GitLab automation for institutional memory",
    version="1.0.0",
    lifespan=lifespan
)


async def _dispatch_mr(payload: dict) -> None:
    """Route a Merge Request Hook payload to the correct agent(s)."""
    action = payload.get("object_attributes", {}).get("action")
    logger.info("MR action: %s", action)

    if action == "merge":
        logger.info("Routing to cortexKEEPER")
        await run_cortexkeeper(payload)

    elif action in ("open", "update"):
        logger.info("Routing to GUARDKEEPER and SPECFORGE compliance")
        await asyncio.gather(
            run_guardkeeper(payload),
            run_spec_compliance(payload),
        )

    else:
        logger.info("MR action '%s' — no agent handles this", action)


def verify_webhook_secret(token: str) -> bool:
    """Verify the GitLab webhook secret token."""
    if not WEBHOOK_SECRET:
        return True
    return hmac.compare_digest(token or "", WEBHOOK_SECRET)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "cortex"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_gitlab_event: str = Header(None),
    x_gitlab_token: str = Header(None),
):
    """
    Main webhook receiver. Routes all GitLab events to the correct agent.
    """
    if not verify_webhook_secret(x_gitlab_token):
        logger.warning("Webhook received with invalid secret token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await request.json()
    logger.info("Received GitLab event: %s", x_gitlab_event)

    try:
        if x_gitlab_event == "Merge Request Hook":
            await _dispatch_mr(payload)

        elif x_gitlab_event == "Note Hook":
            note_body = (payload.get("object_attributes", {}).get("note") or "").lower()
            noteable_type = payload.get("object_attributes", {}).get("noteable_type", "")
            logger.info("Note on %s: %s", noteable_type, note_body[:80])

            if "cortex: promote-to-org" in note_body:
                logger.info("Routing to ORGKEEPER — promote-to-org on %s", noteable_type)
                await run_orgkeeper(payload)

            elif noteable_type == "MergeRequest":
                if "cortex: intentional" in note_body:
                    logger.info("Routing to GUARDKEEPER reply handler — intentional")
                    await run_guardkeeper(payload, reply_type="intentional")
                elif "cortex: accidental" in note_body:
                    logger.info("Routing to GUARDKEEPER reply handler — accidental")
                    await run_guardkeeper(payload, reply_type="accidental")
                elif "cortex: discuss" in note_body:
                    logger.info("Routing to GUARDKEEPER reply handler — discuss")
                    await run_guardkeeper(payload, reply_type="discuss")

            elif noteable_type == "Issue":
                if "cortex: spec approved" in note_body or note_body.strip() == "approved":
                    logger.info("Routing to SPECFORGE spec approval")
                    await handle_spec_approval(payload)
                if "cortex health" in note_body or "@cortex health" in note_body:
                    logger.info("Routing to cortexCAST (triggered by @cortex health)")
                    await run_cortexcast(user_goal=note_body)

        elif x_gitlab_event == "Issue Hook":
            issue_body = payload.get("object_attributes", {}).get("description", "") or ""
            title = payload.get("object_attributes", {}).get("title", "") or ""
            if "@cortex" in issue_body or "@cortex" in title:
                logger.info("Routing to SPECFORGE")
                await run_specforge(payload)
            if "cortex health" in (issue_body + " " + title).lower() or "@cortex health" in (issue_body + title):
                logger.info("Routing to cortexCAST (triggered by @cortex health in issue)")
                await run_cortexcast(user_goal=issue_body + " " + title)

        elif x_gitlab_event == "Member Hook":
            action = payload.get("event_name") or payload.get("action") or ""
            if "added" in action:
                logger.info("Routing to ONBOARDING for new member")
                await run_onboarding(payload)
            else:
                logger.info("Member Hook action '%s' — no action taken", action)

        else:
            logger.info("Unhandled event type: %s", x_gitlab_event)

    except Exception as e:
        logger.error("Error processing webhook: %s", e, exc_info=True)
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": str(e)},
        )

    return JSONResponse(status_code=200, content={"status": "received"})


@app.post("/cortexcast")
async def trigger_cortexcast():
    """
    On-demand trigger for cortexCAST health report.
    Hit this endpoint manually or for demo purposes.
    """
    logger.info("cortexCAST triggered manually via /cortexcast endpoint")
    try:
        await run_cortexcast(user_goal="")
        return JSONResponse(status_code=200, content={"status": "cortexcast complete"})
    except Exception as e:
        logger.error("cortexCAST failed: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("legacy.main:app", host="0.0.0.0", port=PORT, reload=True)