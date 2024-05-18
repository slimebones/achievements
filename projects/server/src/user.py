from orwynn.mongo import Doc, DocField, Udto, OkEvt
from orwynn.sys import Sys
from pykit.err import ValueErr
from pykit.query import Query
from rxcat import Req
from pykit.fcode import code

from src.platform import PLATFORM_TO_PROCESSOR, PLATFORMS

class UserUdto(Udto):
    username: str
    global_completion: float
    platform_to_user_sid: dict[str, str | None]
    platform_to_api_token: dict[str, str | None]
    game_sids: list[str]

class UserDoc(Doc):
    COLLECTION_NAMING = "snake_case"
    FIELDS = [
        DocField(name="username", unique=True),
        DocField(name="game_sids", linked_doc="game_doc")
    ]

    username: str
    global_completion: float = 0.0
    platform_to_user_sid: dict[str, str | None] = {}
    platform_to_api_token: dict[str, str | None] = {}
    game_sids: list[str] = []

    def to_udto(self) -> UserUdto:
        return UserUdto(
            sid=self.sid,
            username=self.username,
            global_completion=self.global_completion,
            platform_to_user_sid=self.platform_to_user_sid,
            platform_to_api_token=self.platform_to_api_token,
            game_sids=self.game_sids)

@code("register_platform_req")
class RegisterPlatformReq(Req):
    user_sid: str
    platform: str
    platform_user_sid: str
    token: str

@code("deregister_platform_req")
class DeregisterPlatformReq(Req):
    user_sid: str
    platform: str

@code("sync_req")
class SyncReq(Req):
    """
    Syncs data for a user with all platforms' APIs.
    """
    user_sid: str

class UserSys(Sys):
    async def enable(self):
        await self._sub(
            RegisterPlatformReq, self._on_register_token)
        await self._sub(
            DeregisterPlatformReq, self._on_deregister_token)
        await self._sub(
            SyncReq, self._sync_req)

    async def _sync_req(self, req: SyncReq):
        user = UserDoc.get(Query.as_search_sid(req.user_sid))
        for platform, api_token in user.platform_to_api_token.items():
            if not api_token:
                continue
            if platform not in PLATFORMS:
                raise ValueErr(f"unrecognized platform {platform}")
            await PLATFORM_TO_PROCESSOR[platform].process(user, api_token)

    async def _on_register_token(self, req: RegisterPlatformReq):
        if req.platform not in PLATFORMS:
            raise ValueErr(f"unrecognized platform {req.platform}")
        UserDoc.get_and_upd(
            Query.as_search_sid(req.user_sid),
            Query.as_upd(set={
                f"platform_to_api_token.{req.platform}": req.token,
                f"platform_to_user_sid.{req.platform}": req.platform_user_sid
            }))
        await self._pub(OkEvt(rsid="").as_res_from_req(req))

    async def _on_deregister_token(self, req: DeregisterPlatformReq):
        if req.platform not in PLATFORMS:
            raise ValueErr(f"unrecognized platform {req.platform}")
        UserDoc.get_and_upd(
            Query.as_search_sid(req.user_sid),
            Query.as_upd(set={
                f"platform_to_api_token.{req.platform}": None}))
        await self._pub(OkEvt(rsid="").as_res_from_req(req))

