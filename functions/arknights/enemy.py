import re
import jieba

from typing import List
from core import log, bot, Message, Chain, exec_before_init
from core.util import find_similar_list, remove_xml_tag, integer, any_match
from core.resource.arknightsGameData import ArknightsGameData

line_height = 16
side_padding = 10


def get_value(key, source):
    for item in key.split('.'):
        if item in source:
            source = source[item]
    return source['m_defined'], integer(source['m_value'])


class Enemy:
    enemies: List[str] = []

    @staticmethod
    @exec_before_init
    async def init_enemies():
        log.info('building enemies names keywords dict...')

        Enemy.enemies = list(ArknightsGameData().enemies.keys())

        with open('resource/enemies.txt', mode='w', encoding='utf-8') as file:
            file.write('\n'.join([f'{name} 500 n' for name in Enemy.enemies]))

        jieba.load_userdict('resource/enemies.txt')

    @classmethod
    def find_enemy(cls, name: str):
        enemies = ArknightsGameData().enemies

        data = enemies[name]['info']
        detail = enemies[name]['data']

        text = '博士，为您找到了敌方档案\n\n\n\n\n\n\n'
        text += '【%s】\n\n' % name
        text += '%s\n\n' % data['description']
        text += '[能力]\n%s\n\n' % remove_xml_tag(data['ability'] or '无')
        text += '[属性]\n耐久 %s | 攻击力 %s | 防御力 %s | 法术抗性 %s\n' % \
                (data['endure'],
                 data['attack'],
                 data['defence'],
                 data['resistance'])

        key_map = {
            'attributes.maxHp': {'title': '生命值', 'value': ''},
            'attributes.atk': {'title': '攻击力', 'value': ''},
            'attributes.def': {'title': '物理防御', 'value': ''},
            'attributes.magicResistance': {'title': '魔法抗性', 'value': ''},
            'attributes.moveSpeed': {'title': '移动速度', 'value': ''},
            'attributes.baseAttackTime': {'title': '攻击间隔', 'value': ''},
            'attributes.hpRecoveryPerSec': {'title': '生命回复/秒', 'value': ''},
            'attributes.massLevel': {'title': '重量', 'value': ''},
            'rangeRadius': {'title': '攻击距离/格', 'value': ''},
            'lifePointReduce': {'title': '进点损失', 'value': ''}
        }

        for item in detail:
            text += '\n[等级 %s 数值]\n' % (item['level'] + 1)
            detail_data = item['enemyData']
            key_index = 0
            for key in key_map:
                defined, value = get_value(key, detail_data)
                if defined:
                    key_map[key]['value'] = value
                else:
                    value = key_map[key]['value']

                text += '%s：%s%s' % (key_map[key]['title'], value, '    ' if key_index % 2 == 0 else '\n')
                key_index += 1
            if detail_data['skills']:
                text += '技能冷却时间：\n'
                for sk in detail_data['skills']:
                    sk_info = (sk['prefabKey'], sk['initCooldown'], sk['cooldown'])
                    text += '    - [%s]\n    -- 初动 %ss，冷却 %ss\n' % sk_info

        icons = [
            {
                'path': 'resource/gamedata/enemy/%s.png' % data['enemyId'],
                'size': 80,
                'pos': (side_padding, side_padding + line_height + int((line_height * 6 - 80) / 2))
            }
        ]

        return text, icons


async def verify(data: Message):
    name = any_match(data.text, Enemy.enemies)
    keyword = any_match(data.text, ['敌人', '敌方'])

    if name or keyword:
        return True, (3 if keyword else 1)
    return False


@bot.on_group_message(function_id='checkEnemy', verify=verify)
async def _(data: Message):
    message = data.text_origin
    words = data.text_cut

    for reg in ['敌人(.*)', '敌方(.*)', '(.*)敌人', '(.*)敌方']:
        r = re.search(re.compile(reg), message)
        if r:
            enemy_name = r.group(1)
            result, rate = find_similar_list(enemy_name, Enemy.enemies, _random=False)
            if result:
                if len(result) == 1:
                    return Chain(data).text_image(*Enemy.find_enemy(result[0]))

                text = '博士，为您搜索到以下敌方单位：\n\n'

                for index, item in enumerate(result):
                    text += f'[{index + 1}] {item}\n'

                text += '\n回复【序号】查询对应的敌方单位资料'

                wait = await data.waiting(Chain(data).text(text))
                if wait:
                    r = re.search(r'(\d+)', wait.text_digits)
                    if r:
                        index = abs(int(r.group(1))) - 1
                        if index >= len(result):
                            index = len(result) - 1

                        return Chain(data).text_image(*Enemy.find_enemy(result[index]))
            else:
                return Chain(data).text('博士，没有找到敌方单位%s的资料呢 >.<' % enemy_name)

    for item in words:
        if item in Enemy.enemies:
            return Chain(data).text_image(*Enemy.find_enemy(item))
