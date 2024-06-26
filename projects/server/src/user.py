from orwynn.mongo import (
    Doc,
    DocField,
    GetDocsReq,
    OkEvt,
    Udto,
    filter_collection_factory,
)
from orwynn.sys import Sys
from pykit.err import ValueErr
from pykit.fcode import code
from pykit.query import Query
from rxcat import Req

from src.platform import (
    PLATFORM_TO_PROCESSOR,
    PLATFORMS,
    PlatformProcessorArgs,
)


class UserUdto(Udto):
    username: str
    global_completion: float
    registered_platforms: list[str]
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
    # todo: platform_to_completion
    registered_platforms: list[str] = []
    platform_to_user_sid: dict[str, str | None] = {}
    platform_to_api_token: dict[str, str | None] = {}
    game_sids: list[str] = []

    def to_udto(self) -> UserUdto:
        return UserUdto(
            sid=self.sid,
            username=self.username,
            global_completion=self.global_completion,
            registered_platforms=self.registered_platforms,
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

@code("register_or_login_user_req")
class RegisterOrLoginUserReq(Req):
    username: str

class UserSys(Sys):
    CommonSubMsgFilters = [
        filter_collection_factory(UserDoc.get_collection())
    ]

    async def enable(self):
        await self._sub(
            RegisterPlatformReq, self._on_register_platform)
        await self._sub(
            DeregisterPlatformReq, self._on_deregister_platform)
        await self._sub(
            SyncReq, self._on_sync_req)
        await self._sub(RegisterOrLoginUserReq, self._on_register_or_login)
        await self._sub(GetDocsReq, self._on_get_docs)

    async def _on_get_docs(self, req: GetDocsReq):
        docs = UserDoc.get_many(req.searchQuery)
        await self._pub(UserDoc.to_got_doc_udtos_evt(req, docs))

    async def _on_register_or_login(self, req: RegisterOrLoginUserReq):
        user = UserDoc.try_get(Query({"username": req.username}))
        if user is None:
            user = UserDoc(username=req.username).create()
        await self._pub(user.to_got_doc_udto_evt(req))

    async def _on_sync_req(self, req: SyncReq):
        user = UserDoc.get(Query.as_search_sid(req.user_sid))
        for platform, api_token in user.platform_to_api_token.items():
            if not api_token:
                continue
            if platform not in PLATFORMS:
                raise ValueErr(f"unrecognized platform {platform}")
            platform_user_sid = user.platform_to_user_sid[platform]
            assert \
                platform_user_sid is not None, \
                "platform user sid should be set if platform api token is set"
            await PLATFORM_TO_PROCESSOR[platform].process(
                PlatformProcessorArgs(
                    api_token=api_token,
                    platform_user_sid=platform_user_sid))
        await self._pub(OkEvt(rsid="").as_res_from_req(req))

    async def _on_register_platform(self, req: RegisterPlatformReq):
        if req.platform not in PLATFORMS:
            raise ValueErr(f"unrecognized platform {req.platform}")
        UserDoc.get_and_upd(
            Query.as_search_sid(req.user_sid),
            Query.as_upd(
                set={
                    f"platform_to_api_token.{req.platform}": req.token,
                    f"platform_to_user_sid.{req.platform}":
                        req.platform_user_sid
                },
                push={
                    "registered_platforms": req.platform
                }))
        await self._pub(OkEvt(rsid="").as_res_from_req(req))

    async def _on_deregister_platform(self, req: DeregisterPlatformReq):
        if req.platform not in PLATFORMS:
            raise ValueErr(f"unrecognized platform {req.platform}")
        UserDoc.get_and_upd(
            Query.as_search_sid(req.user_sid),
            Query.as_upd(
                set={
                    f"platform_to_api_token.{req.platform}": None,
                    f"platform_to_user_sid.{req.platform}": None
                },
                pull={
                    "registered_platforms": req.platform
                }))
        await self._pub(OkEvt(rsid="").as_res_from_req(req))

