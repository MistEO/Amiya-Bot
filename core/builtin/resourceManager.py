from graiax import silkcoder
from core.network.httpSessionClient import HttpSessionClient


class ResourceManager:
    http = HttpSessionClient()

    @classmethod
    async def get_image_id(cls, target, msg_type):
        if type(target) is str:
            with open(target, mode='rb') as file:
                target = file.read()

        return await cls.http.upload_image(target, msg_type)

    @classmethod
    async def get_voice_id(cls, path, msg_type):
        return await cls.http.upload_voice(await silkcoder.encode(path), msg_type)
