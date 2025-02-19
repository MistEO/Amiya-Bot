import re
import time
import asyncio

from typing import List
from core.database import SearchParams, select_for_paginate
from core.database.group import db as group, GroupActive, GroupSetting, GroupNotice, Group as GroupData
from core.database.messages import db as messages
from core.network import response
from core.network.httpServer.auth import AuthManager
from core import http, websocket, custom_chain, log

from .model.group import GroupInfo, GroupTable, GroupStatus, GroupNoticeTable, Notice


class Group:
    @classmethod
    async def get_group_by_pages(cls, items: GroupTable, auth=AuthManager.depends()):
        where = []
        order = ''

        like = {
            'g.group_id': 'group_id',
            'g.group_name': 'group_name'
        }
        equal = {
            'g.permission': 'permission',
            'g2.active': 'active',
            'g3.send_notice': 'send_notice',
            'g3.send_weibo': 'send_weibo'
        }

        for field, item in like.items():
            value = getattr(items.search, item)
            if value:
                where.append(f"{field} like '%{value}%'")

        for field, item in equal.items():
            value = getattr(items.search, item)
            if value:
                where.append(f"{field} = '{value}'")

        if items.search.orderBy:
            field = items.search.orderByField

            if field == 'group_id':
                order = f'order by g.group_id {items.search.orderBy}'
            elif field == 'group_name':
                order = f'order by g.group_name {items.search.orderBy}'
            elif field == 'message_num':
                order = f'order by g4.message_num {items.search.orderBy}'

        if where:
            where = 'where ' + ' and '.join(where)

        sql = re.sub(' +', ' ', f'''
        select g.group_id,
               g.group_name,
               g.permission,
               g2.active,
               g2.sleep_time,
               g3.send_notice,
               g3.send_weibo
        from `group` g
                 left join group_active g2 on g.group_id = g2.group_id
                 left join group_setting g3 on g.group_id = g3.group_id
                  {where if where else ''} {order if order else ''}
        '''.strip().replace('\n', ' '))

        fields = [
            'group_id',
            'group_name',
            'permission',
            'active',
            'sleep_time',
            'send_notice',
            'send_weibo'
        ]

        limit = (items.page - 1) * items.pageSize
        offset = items.page * items.pageSize

        res = group.execute_sql(sql).fetchall()
        res = [{fields[i]: n for i, n in enumerate(row)} for row in res]
        page = res[limit:offset]

        gid = ', '.join([n['group_id'] for n in page])
        if gid:
            msg = messages.execute_sql(
                f'select group_id, count(*) from message_record where group_id in ({gid}) group by group_id'
            ).fetchall()
            msg = {str(n[0]): n[1] for n in msg}

            for item in page:
                item['message_num'] = 0
                if item['group_id'] in msg:
                    item['message_num'] = msg[item['group_id']]

        return response({'count': len(res), 'data': page})

    @classmethod
    async def refresh_group_list(cls, auth=AuthManager.depends()):
        group_list = await http.get_group_list()

        GroupData.truncate_table()
        GroupData.batch_insert(group_list)

        return response(message=f'同步完成，共 {len(group_list)} 个群。')

    @classmethod
    async def get_member_list(cls, auth=AuthManager.depends()):
        return response(code=0, message='接口未开放')

    @classmethod
    async def change_group_status(cls, items: GroupStatus, auth=AuthManager.depends()):
        if items.active is not None:
            GroupActive.insert_or_update(
                insert={
                    'group_id': items.group_id,
                    'active': items.active
                },
                update={
                    GroupActive.active: items.active
                },
                conflict_target=[GroupActive.group_id]
            )
        else:
            for name in ['send_notice', 'send_weibo']:
                value = getattr(items, name)
                if name is not None:
                    GroupSetting.insert_or_update(
                        insert={
                            name: value,
                            'group_id': items.group_id
                        },
                        update={
                            getattr(GroupSetting, name): value
                        },
                        conflict_target=[GroupSetting.group_id]
                    )

        return response(message='修改成功')

    @classmethod
    async def leave_group(cls, items: GroupInfo, auth=AuthManager.depends()):
        members = await http.leave_group(items.group_id)
        return response(members)

    @classmethod
    async def get_group_notice_by_pages(cls, items: GroupNoticeTable, auth=AuthManager.depends()):
        search = SearchParams(
            items.search,
            contains=['content', 'send_user']
        )

        data, count = select_for_paginate(GroupNotice,
                                          search,
                                          page=items.page,
                                          page_size=items.pageSize)

        return response({'count': count, 'data': data})

    @classmethod
    async def push_notice(cls, items: Notice, auth=AuthManager.depends()):
        group_list = await http.get_group_list()

        disabled: List[GroupSetting] = GroupSetting.select().where(GroupSetting.send_notice == 0)
        disabled: List[str] = [n.group_id for n in disabled]

        success = 0
        for item in group_list:
            group_id = item['group_id']
            group_name = item['group_name']

            if str(group_id) in disabled:
                continue

            async with log.catch('push error:'):
                data = custom_chain(group_id=int(group_id))
                data.text(f'亲爱的{group_name}的博士们，有来自管理员{auth.user_id}的公告：\n\n{items.content}')

                await websocket.send(data)

                success += 1

            await asyncio.sleep(0.5)

        GroupNotice.create(
            content=items.content,
            send_time=int(time.time()),
            send_user=auth.user_id
        )

        return response(message=f'公告推送完毕，成功：{success}/{len(group_list)}')

    @classmethod
    async def del_notice(cls, items: Notice, auth=AuthManager.depends()):
        GroupNotice.delete().where(GroupNotice.notice_id == items.notice_id).execute()
        return response(message='删除成功')
