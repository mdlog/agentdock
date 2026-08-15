import json
import os
from typing import Any

import boto3
import httpx


class B402Unavailable(RuntimeError):
    pass


class B402Adapter:
    """Strict boundary for Binance B402 V2. Never treats browser claims as proof."""

    required = ("B402_BASE_URL", "B402_CLIENT_ID", "B402_ACCESS_TOKEN", "B402_RSA_PRIVATE_KEY_PATH")

    @property
    def ready(self) -> bool:
        return all(os.environ.get(key) for key in self.required)

    async def supported(self) -> dict[str, Any]:
        if not self.ready:
            raise B402Unavailable("Binance B402 partner credentials are not configured")
        raise B402Unavailable("Merchant-specific B402 V2 signing schema must be activated during Binance onboarding")

    async def verify_and_settle(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if not self.ready:
            raise B402Unavailable("Binance B402 partner credentials are not configured")
        raise B402Unavailable("Merchant-specific B402 V2 signing schema must be activated during Binance onboarding")


class ArtifactStore:
    required = ("S3_ENDPOINT_URL", "S3_REGION", "S3_BUCKET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")

    @property
    def ready(self) -> bool:
        return all(os.environ.get(key) for key in self.required)

    async def save(self, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        if not self.ready:
            return {"mode": "mongodb", "payload": result}
        client = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"], region_name=os.environ["S3_REGION"])
        key = f"tasks/{task_id}/result.json"
        client.put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=json.dumps(result).encode(), ContentType="application/json", ServerSideEncryption="AES256")
        return {"mode": "object_storage", "key": key}


async def registry_health() -> tuple[bool, bool]:
    rpc_url = os.environ.get("BSC_RPC_URL")
    registry = os.environ.get("ERC8004_IDENTITY_REGISTRY")
    if not rpc_url or not registry:
        return False, False
    async with httpx.AsyncClient(timeout=8) as client:
        chain = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
        if chain.json().get("result") != "0x61":
            return False, False
        code = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "eth_getCode", "params": [registry, "latest"]})
        return True, code.json().get("result", "0x") != "0x"