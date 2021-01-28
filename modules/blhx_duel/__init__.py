import asyncio
import base64
import os
import random
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO

from hoshino import Service, priv
from hoshino.modules.priconne import chara_blhx,_blhx_data
from hoshino.typing import *
from hoshino.typing import CQEvent
from hoshino.util import DailyNumberLimiter, concat_pic

sv = Service('blhx-duel', enable_on_default=True)
DUEL_DB_PATH = os.path.expanduser('~/.hoshino/blhx_duel.db')
SCORE_DB_PATH = os.path.expanduser('~/.hoshino/blhx_running_counter.db')
BLACKLIST_ID = []  # 黑名单ID
WAIT_TIME = 30  # 对战接受等待时间
DUEL_SUPPORT_TIME = 20
DB_PATH = os.path.expanduser("~/.hoshino/blhx_duel.db")
SIGN_DAILY_LIMIT = 1  # 机器人每天签到的次数
RESET_HOUR = 0  # 每日使用次数的重置时间，0代表凌晨0点，1代表凌晨1点，以此类推
SIGN_BONUS = 10  # 签到获得量
GACHA_COST = 30  # 抽老婆需求
ZERO_GET_AMOUNT = 5  # 没钱补给量
Addgirlfail = [
    '你参加了一场指挥官舞会，热闹的舞会场今天竟然没人同你跳舞。',
    '你邀请到了心仪的舰娘跳舞，可是跳舞时却踩掉了她的鞋，她生气的离开了。',
    '你为这次舞会准备了很久，结果一不小心在桌子上睡着了，醒来时只看到了过期的邀请函。',
    '你参加了一场指挥官舞会，可是舞会上只有一名男性向你一直眨眼。',
    '你准备参加一场指挥官舞会，可惜因为忘记穿礼服，被拦在了门外。',
    '你沉浸在舞会的美食之中，忘了此行的目的。',
    '你本准备参加舞会，却被会长拉去出了一晚上刀。'
]
Addgirlsuccess = [
    '你参加了一场指挥官舞会，你优雅的舞姿让每位年轻女孩都望向了你。',
    '你参加了一场指挥官舞会，你的帅气使你成为了舞会的宠儿。',
    '你在舞会门口就遇到了一位女孩，你挽着她的手走进了舞会。',
    '你在舞会的闲聊中无意中谈到了自己显赫的家室，你成为了舞会的宠儿。',
    '没有人比你更懂舞会，每一个女孩都为你的风度倾倒。'
]


# noinspection SqlResolve
class RecordDAO:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._create_table()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS limiter"
                "(key TEXT NOT NULL, num INT NOT NULL, date INT, PRIMARY KEY(key))"
            )

    def exist_check(self, key):
        try:
            key = str(key)
            with self.connect() as conn:
                conn.execute("INSERT INTO limiter (key,num,date) VALUES (?, 0,-1)", (key,), )
            return
        except:
            return

    def get_num(self, key):
        self.exist_check(key)
        key = str(key)
        with self.connect() as conn:
            r = conn.execute(
                "SELECT num FROM limiter WHERE key=? ", (key,)
            ).fetchall()
            r2 = r[0]
        return r2[0]

    def clear_key(self, key):
        key = str(key)
        self.exist_check(key)
        with self.connect() as conn:
            conn.execute("UPDATE limiter SET num=0 WHERE key=?", (key,), )
        return

    def increment_key(self, key, num):
        self.exist_check(key)
        key = str(key)
        with self.connect() as conn:
            conn.execute("UPDATE limiter SET num=num+? WHERE key=?", (num, key,))
        return

    def get_date(self, key):
        self.exist_check(key)
        key = str(key)
        with self.connect() as conn:
            r = conn.execute(
                "SELECT date FROM limiter WHERE key=? ", (key,)
            ).fetchall()
            r2 = r[0]
        return r2[0]

    def set_date(self, date, key):
        print(date)
        self.exist_check(key)
        key = str(key)
        with self.connect() as conn:
            conn.execute("UPDATE limiter SET date=? WHERE key=?", (date, key,), )
        return


db = RecordDAO(DB_PATH)


class DailyAmountLimiter(DailyNumberLimiter):
    def __init__(self, types, max_num, reset_hour):
        super().__init__(max_num)
        self.reset_hour = reset_hour
        self.type = types

    def check(self, key) -> bool:
        now = datetime.now(self.tz)
        key = list(key)
        key.append(self.type)
        key = tuple(key)
        day = (now - timedelta(hours=self.reset_hour)).day
        if day != db.get_date(key):
            db.set_date(day, key)
            db.clear_key(key)
        return bool(db.get_num(key) < self.max)

    def check10(self, key) -> bool:
        now = datetime.now(self.tz)
        key = list(key)
        key.append(self.type)
        key = tuple(key)
        day = (now - timedelta(hours=self.reset_hour)).day
        if day != db.get_date(key):
            db.set_date(day, key)
            db.clear_key(key)
        return bool(db.get_num(key) < 10)

    def get_num(self, key):
        key = list(key)
        key.append(self.type)
        key = tuple(key)
        return db.get_num(key)

    def increase(self, key, num=1):
        key = list(key)
        key.append(self.type)
        key = tuple(key)
        db.increment_key(key, num)

    def reset(self, key):
        key = list(key)
        key.append(self.type)
        key = tuple(key)
        db.clear_key(key)


daily_sign_limiter = DailyAmountLimiter("sign", SIGN_DAILY_LIMIT, RESET_HOUR)


# 用于与赛跑红尖尖互通
class ScoreCounter2:
    def __init__(self):
        os.makedirs(os.path.dirname(SCORE_DB_PATH), exist_ok=True)
        self._create_table()

    def _connect(self):
        return sqlite3.connect(SCORE_DB_PATH)

    def _create_table(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS SCORECOUNTER
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           SCORE           INT    NOT NULL,
                           PRIMARY KEY(GID, UID));''')
        except:
            raise Exception('创建表发生错误')

    def _add_score(self, gid, uid, score):
        try:
            current_score = self._get_score(gid, uid)
            conn = self._connect()
            conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, current_score + score))
            conn.commit()
        except:
            raise Exception('更新表发生错误')

    def _reduce_score(self, gid, uid, score):
        try:
            current_score = self._get_score(gid, uid)
            if current_score >= score:
                conn = self._connect()
                conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, current_score - score))
                conn.commit()
            else:
                conn = self._connect()
                conn.execute("INSERT OR REPLACE INTO SCORECOUNTER (GID,UID,SCORE) \
                                VALUES (?,?,?)", (gid, uid, 0))
                conn.commit()
        except:
            raise Exception('更新表发生错误')

    def _get_score(self, gid, uid):
        try:
            r = self._connect().execute("SELECT SCORE FROM SCORECOUNTER WHERE GID=? AND UID=?", (gid, uid)).fetchone()
            return 0 if r is None else r[0]
        except:
            raise Exception('查找表发生错误')

    # 判断红尖尖是否足够下注
    def _judge_score(self, gid, uid, score):
        try:
            current_score = self._get_score(gid, uid)
            if current_score >= score:
                return 1
            else:
                return 0
        except Exception as e:
            raise Exception(str(e))

        # 记录指挥官相关数据


class DuelCounter:
    def __init__(self):
        os.makedirs(os.path.dirname(DUEL_DB_PATH), exist_ok=True)
        self._create_chara_blhxtable()
        self._create_uidtable()
        self._create_leveltable()

    def _connect(self):
        return sqlite3.connect(DUEL_DB_PATH)

    def _create_chara_blhxtable(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS chara_blhxTABLE
                          (GID             INT    NOT NULL,
                           CID             INT    NOT NULL,
                           UID           INT    NOT NULL,
                           PRIMARY KEY(GID, CID));''')
        except:
            raise Exception('创建角色表发生错误')

    def _create_uidtable(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS UIDTABLE
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           CID           INT    NOT NULL,
                           NUM           INT    NOT NULL,
                           PRIMARY KEY(GID, UID, CID));''')
        except:
            raise Exception('创建UID表发生错误')

    def _create_leveltable(self):
        try:
            self._connect().execute('''CREATE TABLE IF NOT EXISTS LEVELTABLE
                          (GID             INT    NOT NULL,
                           UID             INT    NOT NULL,
                           LEVEL           INT    NOT NULL,
                           
                           PRIMARY KEY(GID, UID));''')
        except:
            raise Exception('创建UID表发生错误')

    def _get_card_owner(self, gid, cid):
        try:
            r = self._connect().execute("SELECT UID FROM chara_blhxTABLE WHERE GID=? AND CID=?", (gid, cid)).fetchone()
            return 0 if r is None else r[0]
        except:
            raise Exception('查找角色归属发生错误')

    def _set_card_owner(self, gid, cid, uid):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO chara_blhxTABLE (GID, CID, UID) VALUES (?, ?, ?)",
                (gid, cid, uid),
            )

    def _delete_card_owner(self, gid, cid):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chara_blhxTABLE  WHERE GID=? AND CID=?",
                (gid, cid),
            )

            # 查询已被邀请的舰娘列表

    def _get_card_list(self, gid):
        with self._connect() as conn:
            r = conn.execute(
                f"SELECT CID FROM chara_blhxTABLE WHERE GID={gid}").fetchall()
            return [c[0] for c in r] if r else {}

    def _get_level(self, gid, uid):
        try:
            r = self._connect().execute("SELECT LEVEL FROM LEVELTABLE WHERE GID=? AND UID=?", (gid, uid)).fetchone()
            return 0 if r is None else r[0]
        except:
            raise Exception('查找等级发生错误')

    def _get_cards(self, gid, uid):
        with self._connect() as conn:
            r = conn.execute(
                "SELECT CID, NUM FROM UIDTABLE WHERE GID=? AND UID=? AND NUM>0", (gid, uid)
            ).fetchall()
        return [c[0] for c in r] if r else {}

    def _get_card_num(self, gid, uid, cid):
        with self._connect() as conn:
            r = conn.execute(
                "SELECT NUM FROM UIDTABLE WHERE GID=? AND UID=? AND CID=?", (gid, uid, cid)
            ).fetchone()
            return r[0] if r else 0

    def _add_card(self, gid, uid, cid, increment=1):
        num = self._get_card_num(gid, uid, cid)
        num += increment
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO UIDTABLE (GID, UID, CID, NUM) VALUES (?, ?, ?, ?)",
                (gid, uid, cid, num),
            )
        self._set_card_owner(gid, cid, uid)

    def _delete_card(self, gid, uid, cid, increment=1):
        num = self._get_card_num(gid, uid, cid)
        num -= increment
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO UIDTABLE (GID, UID, CID, NUM) VALUES (?, ?, ?, ?)",
                (gid, uid, cid, num),
            )
        self._delete_card_owner(gid, cid)

    def _add_level(self, gid, uid, increment=1):
        level = self._get_level(gid, uid)
        level += increment
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO LEVELTABLE (GID, UID, LEVEL) VALUES (?, ?, ?)",
                (gid, uid, level),
            )

    def _reduce_level(self, gid, uid, increment=1):
        level = self._get_level(gid, uid)
        level -= increment
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO LEVELTABLE (GID, UID, LEVEL) VALUES (?, ?, ?)",
                (gid, uid, level),
            )

    def _set_level(self, gid, uid, level):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO LEVELTABLE (GID, UID, LEVEL) VALUES (?, ?, ?)",
                (gid, uid, level),
            )

        # 记录决斗和下注数据


class DuelJudger:
    def __init__(self):
        self.on = {}
        self.accept_on = {}
        self.support_on = {}
        self.fire_on = {}
        self.deadnum = {}
        self.support = {}
        self.turn = {}
        self.duelid = {}
        self.isaccept = {}
        self.hasfired_on = {}

    def set_support(self, gid):
        self.support[gid] = {}

    def get_support(self, gid):
        return self.support[gid] if self.support.get(gid) is not None else 0

    def add_support(self, gid, uid, id, score):
        self.support[gid][uid] = [id, score]

    def get_support_id(self, gid, uid):
        if self.support[gid].get(uid) is not None:
            return self.support[gid][uid][0]
        else:
            return 0

    def get_support_score(self, gid, uid):
        if self.support[gid].get(uid) is not None:
            return self.support[gid][uid][1]
        else:
            return 0

    # 五个开关：决斗，接受，下注， 开枪, 是否已经开枪

    def get_on_off_status(self, gid):
        return self.on[gid] if self.on.get(gid) is not None else False

    def turn_on(self, gid):
        self.on[gid] = True

    def turn_off(self, gid):
        self.on[gid] = False

    def get_on_off_accept_status(self, gid):
        return self.accept_on[gid] if self.accept_on.get(gid) is not None else False

    def turn_on_accept(self, gid):
        self.accept_on[gid] = True

    def turn_off_accept(self, gid):
        self.accept_on[gid] = False

    def get_on_off_support_status(self, gid):
        return self.support_on[gid] if self.support_on.get(gid) is not None else False

    def turn_on_support(self, gid):
        self.support_on[gid] = True

    def turn_off_support(self, gid):
        self.support_on[gid] = False

    def get_on_off_fire_status(self, gid):
        return self.fire_on[gid] if self.fire_on.get(gid) is not None else False

    def turn_on_fire(self, gid):
        self.fire_on[gid] = True

    def turn_off_fire(self, gid):
        self.fire_on[gid] = False

    def get_on_off_hasfired_status(self, gid):
        return self.hasfired_on[gid] if self.hasfired_on.get(gid) is not None else False

    def turn_on_hasfired(self, gid):
        self.hasfired_on[gid] = True

    def turn_off_hasfired(self, gid):
        self.hasfired_on[gid] = False

    # 记录决斗者id
    def init_duelid(self, gid):
        self.duelid[gid] = []

    def set_duelid(self, gid, id1, id2):
        self.duelid[gid] = [id1, id2]

    def get_duelid(self, gid):
        return self.duelid[gid] if self.accept_on.get(gid) is not None else [0, 0]
        # 查询一个决斗者是1号还是2号

    def get_duelnum(self, gid, uid):
        return self.duelid[gid].index(uid) + 1

    # 记录由谁开枪
    def init_turn(self, gid):
        self.turn[gid] = 1

    def get_turn(self, gid):
        return self.turn[gid] if self.turn[gid] is not None else 0

    def change_turn(self, gid):
        if self.get_turn(gid) == 1:
            self.turn[gid] = 2
            return 2
        else:
            self.turn[gid] = 1
            return 1

    # 记录子弹位置
    def init_deadnum(self, gid):
        self.deadnum[gid] = None

    def set_deadnum(self, gid, num):
        self.deadnum[gid] = num

    def get_deadnum(self, gid):
        return self.deadnum[gid] if self.deadnum[gid] is not None else False

    # 记录是否接受
    def init_isaccept(self, gid):
        self.isaccept[gid] = False

    def on_isaccept(self, gid):
        self.isaccept[gid] = True

    def off_isaccept(self, gid):
        self.isaccept[gid] = False

    def get_isaccept(self, gid):
        return self.isaccept[gid] if self.isaccept[gid] is not None else False


duel_judger = DuelJudger()


# 随机生成一个blhx角色id
def get_blhx_id():
    chara_blhx_id_list = list(_blhx_data.CHARA_NAME.keys())
    while True:
        random.shuffle(chara_blhx_id_list)
        if chara_blhx_id_list[0] not in BLACKLIST_ID: break
    return chara_blhx_id_list[0]


# 生成没被约过的角色列表
def get_newgirl_list(gid):
    chara_blhx_id_list = list(_blhx_data.CHARA_NAME.keys())
    duel = DuelCounter()
    old_list = duel._get_card_list(gid)
    new_list = []
    for card in chara_blhx_id_list:
        if card not in BLACKLIST_ID and card not in old_list:
            new_list.append(card)
    return new_list


# 取等级名
def get_noblename(level: int):
    namedict = {'1': '1级指挥官', '2': '2级指挥官', '3': '3级指挥官', '4': '4级指挥官', '5': '5级指挥官', '6': '6级指挥官', '7': '7级指挥官',
                '8': '8级指挥官', '9': '9级指挥官', '10': '10级指挥官', '11': '11级指挥官', '12': '12级指挥官', '13': '13级指挥官',
                '14': '14级指挥官', '15': '15级指挥官', '16': '16级指挥官', '17': '17级指挥官', '18': '18级指挥官', '19': '19级指挥官',
                '20': '20级指挥官', '21': '21级指挥官', '22': '22级指挥官', '23': '23级指挥官', '24': '24级指挥官', '25': '25级指挥官',
                '26': '26级指挥官', '27': '27级指挥官', '28': '28级指挥官', '29': '29级指挥官', '30': '30级指挥官', '31': '31级指挥官',
                '32': '32级指挥官', '33': '33级指挥官', '34': '34级指挥官', '35': '35级指挥官', '36': '36级指挥官', '37': '37级指挥官',
                '38': '38级指挥官', '39': '39级指挥官', '40': '40级指挥官', '41': '41级指挥官', '42': '42级指挥官', '43': '43级指挥官',
                '44': '44级指挥官', '45': '45级指挥官', '46': '46级指挥官', '47': '47级指挥官', '48': '48级指挥官', '49': '49级指挥官',
                '50': '50级指挥官', '51': '51级指挥官', '52': '52级指挥官', '53': '53级指挥官', '54': '54级指挥官', '55': '55级指挥官',
                '56': '56级指挥官', '57': '57级指挥官', '58': '58级指挥官', '59': '59级指挥官', '60': '60级指挥官', '61': '61级指挥官',
                '62': '62级指挥官', '63': '63级指挥官', '64': '64级指挥官', '65': '65级指挥官', '66': '66级指挥官', '67': '67级指挥官',
                '68': '68级指挥官', '69': '69级指挥官', '70': '70级指挥官', '71': '71级指挥官', '72': '72级指挥官', '73': '73级指挥官',
                '74': '74级指挥官', '75': '75级指挥官', '76': '76级指挥官', '77': '77级指挥官', '78': '78级指挥官', '79': '79级指挥官',
                '80': '80级指挥官', '81': '81级指挥官', '82': '82级指挥官', '83': '83级指挥官', '84': '84级指挥官', '85': '85级指挥官',
                '86': '86级指挥官', '87': '87级指挥官', '88': '88级指挥官', '89': '89级指挥官', '90': '90级指挥官', '91': '91级指挥官',
                '92': '92级指挥官', '93': '93级指挥官', '94': '94级指挥官', '95': '95级指挥官', '96': '96级指挥官', '97': '97级指挥官',
                '98': '98级指挥官', '99': '99级指挥官', '100': '100级指挥官', '101': '101级指挥官', '102': '102级指挥官', '103': '103级指挥官',
                '104': '104级指挥官', '105': '105级指挥官', '106': '106级指挥官', '107': '107级指挥官', '108': '108级指挥官',
                '109': '109级指挥官', '110': '110级指挥官', '111': '111级指挥官', '112': '112级指挥官', '113': '113级指挥官',
                '114': '114级指挥官', '115': '115级指挥官', '116': '116级指挥官', '117': '117级指挥官', '118': '118级指挥官',
                '119': '119级指挥官', '120': '120级指挥官', '121': '121级指挥官', '122': '122级指挥官', '123': '123级指挥官',
                '124': '124级指挥官', '125': '125级指挥官', '126': '126级指挥官', '127': '127级指挥官', '128': '128级指挥官',
                '129': '129级指挥官', '130': '130级指挥官', '131': '131级指挥官', '132': '132级指挥官', '133': '133级指挥官',
                '134': '134级指挥官', '135': '135级指挥官', '136': '136级指挥官', '137': '137级指挥官', '138': '138级指挥官',
                '139': '139级指挥官', '140': '140级指挥官', '141': '141级指挥官', '142': '142级指挥官', '143': '143级指挥官',
                '144': '144级指挥官', '145': '145级指挥官', '146': '146级指挥官', '147': '147级指挥官', '148': '148级指挥官',
                '149': '149级指挥官', '150': '150级指挥官', '151': '151级指挥官', '152': '152级指挥官', '153': '153级指挥官',
                '154': '154级指挥官', '155': '155级指挥官', '156': '156级指挥官', '157': '157级指挥官', '158': '158级指挥官',
                '159': '159级指挥官', '160': '160级指挥官', '161': '161级指挥官', '162': '162级指挥官', '163': '163级指挥官',
                '164': '164级指挥官', '165': '165级指挥官', '166': '166级指挥官', '167': '167级指挥官', '168': '168级指挥官',
                '169': '169级指挥官', '170': '170级指挥官', '171': '171级指挥官', '172': '172级指挥官', '173': '173级指挥官',
                '174': '174级指挥官', '175': '175级指挥官', '176': '176级指挥官', '177': '177级指挥官', '178': '178级指挥官',
                '179': '179级指挥官', '180': '180级指挥官', '181': '181级指挥官', '182': '182级指挥官', '183': '183级指挥官',
                '184': '184级指挥官', '185': '185级指挥官', '186': '186级指挥官', '187': '187级指挥官', '188': '188级指挥官',
                '189': '189级指挥官', '190': '190级指挥官', '191': '191级指挥官', '192': '192级指挥官', '193': '193级指挥官',
                '194': '194级指挥官', '195': '195级指挥官', '196': '196级指挥官', '197': '197级指挥官', '198': '198级指挥官',
                '199': '199级指挥官', '200': '200级指挥官'}
    return namedict[str(level)]


# 返回等级对应的舰娘数
def get_girlnum(level: int):
    numdict = {'1': 3, '2': 4, '3': 5, '4': 6, '5': 7, '6': 8, '7': 9, '8': 10, '9': 11, '10': 12, '11': 13, '12': 14,
               '13': 15, '14': 16, '15': 17, '16': 18, '17': 19, '18': 20, '19': 21, '20': 22, '21': 23, '22': 24,
               '23': 25, '24': 26, '25': 27, '26': 28, '27': 29, '28': 30, '29': 31, '30': 32, '31': 33, '32': 34,
               '33': 35, '34': 36, '35': 37, '36': 38, '37': 39, '38': 40, '39': 41, '40': 42, '41': 43, '42': 44,
               '43': 45, '44': 46, '45': 47, '46': 48, '47': 49, '48': 50, '49': 51, '50': 52, '51': 53, '52': 54,
               '53': 55, '54': 56, '55': 57, '56': 58, '57': 59, '58': 60, '59': 61, '60': 62, '61': 63, '62': 64,
               '63': 65, '64': 66, '65': 67, '66': 68, '67': 69, '68': 70, '69': 71, '70': 72, '71': 73, '72': 74,
               '73': 75, '74': 76, '75': 77, '76': 78, '77': 79, '78': 80, '79': 81, '80': 82, '81': 83, '82': 84,
               '83': 85, '84': 86, '85': 87, '86': 88, '87': 89, '88': 90, '89': 91, '90': 92, '91': 93, '92': 94,
               '93': 95, '94': 96, '95': 97, '96': 98, '97': 99, '98': 100, '99': 101, '100': 102, '101': 103,
               '102': 104, '103': 105, '104': 106, '105': 107, '106': 108, '107': 109, '108': 110, '109': 111,
               '110': 112, '111': 113, '112': 114, '113': 115, '114': 116, '115': 117, '116': 118, '117': 119,
               '118': 120, '119': 121, '120': 122, '121': 123, '122': 124, '123': 125, '124': 126, '125': 127,
               '126': 128, '127': 129, '128': 130, '129': 131, '130': 132, '131': 133, '132': 134, '133': 135,
               '134': 136, '135': 137, '136': 138, '137': 139, '138': 140, '139': 141, '140': 142, '141': 143,
               '142': 144, '143': 145, '144': 146, '145': 147, '146': 148, '147': 149, '148': 150, '149': 151,
               '150': 152, '151': 153, '152': 154, '153': 155, '154': 156, '155': 157, '156': 158, '157': 159,
               '158': 160, '159': 161, '160': 162, '161': 163, '162': 164, '163': 165, '164': 166, '165': 167,
               '166': 168, '167': 169, '168': 170, '169': 171, '170': 172, '171': 173, '172': 174, '173': 175,
               '174': 176, '175': 177, '176': 178, '177': 179, '178': 180, '179': 181, '180': 182, '181': 183,
               '182': 184, '183': 185, '184': 186, '185': 187, '186': 188, '187': 189, '188': 190, '189': 191,
               '190': 192, '191': 193, '192': 194, '193': 195, '194': 196, '195': 197, '196': 198, '197': 199,
               '198': 200, '199': 201, '200': 202}
    return numdict[str(level)]


# 返回升级到等级所需要的红尖尖数
def get_noblescore(level: int):
    numdict = {'1': 0, '2': 5, '3': 11, '4': 18, '5': 26, '6': 36, '7': 48, '8': 62, '9': 79, '10': 99, '11': 122,
               '12': 149, '13': 180, '14': 215, '15': 255, '16': 300, '17': 350, '18': 406, '19': 468, '20': 536,
               '21': 611, '22': 693, '23': 782, '24': 879, '25': 984, '26': 1097, '27': 1219, '28': 1350, '29': 1490,
               '30': 1640, '31': 1800, '32': 1970, '33': 2151, '34': 2343, '35': 2546, '36': 2761, '37': 2988,
               '38': 3227, '39': 3479, '40': 3744, '41': 4022, '42': 4314, '43': 4620, '44': 4940, '45': 5275,
               '46': 5625, '47': 5990, '48': 6371, '49': 6768, '50': 7181, '51': 7611, '52': 8067, '53': 8549,
               '54': 9058, '55': 9594, '56': 10158, '57': 10750, '58': 11371, '59': 12021, '60': 12701, '61': 13411,
               '62': 14152, '63': 14924, '64': 15728, '65': 16564, '66': 17433, '67': 18335, '68': 19271, '69': 20241,
               '70': 21246, '71': 22286, '72': 23398, '73': 24583, '74': 25842, '75': 27176, '76': 28586, '77': 30073,
               '78': 31638, '79': 33282, '80': 35006, '81': 36811, '82': 38698, '83': 40668, '84': 42722, '85': 44861,
               '86': 47086, '87': 49398, '88': 51798, '89': 54287, '90': 56866, '91': 59536, '92': 62390, '93': 65430,
               '94': 68658, '95': 72076, '96': 75686, '97': 79490, '98': 83490, '99': 87688, '100': 92086, '101': 96686,
               '102': 101490, '103': 106500, '104': 111718, '105': 117146, '106': 122786, '107': 128640, '108': 134710,
               '109': 140998, '110': 147506, '111': 154236, '112': 161302, '113': 168707, '114': 176454, '115': 184546,
               '116': 192986, '117': 201777, '118': 210922, '119': 220424, '120': 230286, '121': 240511, '122': 251099,
               '123': 262053, '124': 273376, '125': 285071, '126': 297141, '127': 309589, '128': 322418, '129': 335631,
               '130': 349231, '131': 363221, '132': 377735, '133': 392777, '134': 408351, '135': 424461, '136': 441111,
               '137': 458305, '138': 476047, '139': 494341, '140': 513191, '141': 532601, '142': 552575, '143': 573117,
               '144': 594231, '145': 615921, '146': 638191, '147': 661045, '148': 684487, '149': 708521, '150': 733151,
               '151': 758381, '152': 784366, '153': 811111, '154': 838621, '155': 866901, '156': 895956, '157': 925791,
               '158': 956411, '159': 987821, '160': 1020026, '161': 1053031, '162': 1086841, '163': 1121461,
               '164': 1156896, '165': 1193151, '166': 1230231, '167': 1268141, '168': 1306886, '169': 1346471,
               '170': 1386901, '171': 1428181, '172': 1470487, '173': 1513825, '174': 1558201, '175': 1603621,
               '176': 1650091, '177': 1697617, '178': 1746205, '179': 1795861, '180': 1846591, '181': 1898401,
               '182': 1951297, '183': 2005285, '184': 2060371, '185': 2116561, '186': 2173861, '187': 2232277,
               '188': 2291815, '189': 2352481, '190': 2414281, '191': 2477221, '192': 2541498, '193': 2607119,
               '194': 2674091, '195': 2742421, '196': 2812116, '197': 2883183, '198': 2955629, '199': 3029461,
               '200': 3104686}
    return numdict[str(level)]


@sv.on_fullmatch('指挥官签到')
async def noblelogin(bot, ev: CQEvent):
    gid = ev.group_id
    uid = ev.user_id
    guid = gid, uid
    if not daily_sign_limiter.check(guid):
        await bot.send(ev, '今天已经签到过了哦，明天再来吧。', at_sender=True)
        return
    duel = DuelCounter()
    if duel._get_level(gid, uid) == 0:
        msg = '您还未在本群创建过指挥官，请发送 创建指挥官 开始您的指挥官之旅。'
        await bot.send(ev, msg, at_sender=True)
        return
    score_counter = ScoreCounter2()
    daily_sign_limiter.increase(guid)
    score_counter._add_score(gid, uid, SIGN_BONUS)
    level = duel._get_level(gid, uid)
    noblename = get_noblename(level)
    score = score_counter._get_score(gid, uid)
    msg = f'签到成功！已领取{SIGN_BONUS}红尖尖。\n{noblename}，您现在共有{score}红尖尖。'
    await bot.send(ev, msg, at_sender=True)


@sv.on_fullmatch('创建指挥官')
async def add_noble(bot, ev: CQEvent):
    try:
        gid = ev.group_id
        uid = ev.user_id
        duel = DuelCounter()
        if duel._get_level(gid, uid) != 0:
            msg = '您已经在本群创建过指挥官了，请发送 查询指挥官 查询。'
            await bot.send(ev, msg, at_sender=True)
            return
        else:
            cid = get_blhx_id()
            # 防止情人重复
            while duel._get_card_owner(gid, cid) != 0:
                cid = get_blhx_id()
            duel._add_card(gid, uid, cid)
            c = chara_blhx.fromid(cid)
            duel._set_level(gid, uid, 1)
            msg = f'\n创建指挥官成功！\n您的初始等级为1级\n可以拥有10名舰娘。\n为您分配的初始舰娘为：{c.name}{c.icon.cqcode}'
            await bot.send(ev, msg, at_sender=True)
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))


@sv.on_fullmatch(['查询指挥官', '我的指挥官'])
async def inquire_noble(bot, ev: CQEvent):
    gid = ev.group_id
    uid = ev.user_id
    duel = DuelCounter()
    score_counter = ScoreCounter2()
    if duel._get_level(gid, uid) == 0:
        msg = '您还未在本群创建过指挥官，请发送 创建指挥官 开始您的指挥官之旅。'
        await bot.send(ev, msg, at_sender=True)
        return
    level = duel._get_level(gid, uid)
    noblename = get_noblename(level)
    girlnum = get_girlnum(level)
    score = score_counter._get_score(gid, uid)
    chara_blhxlist = []

    cidlist = duel._get_cards(gid, uid)
    cidnum = len(cidlist)
    if cidnum == 0:
        msg = f'''
╔                          ╗
  您的等级为{noblename}
  您的红尖尖为{score}
  您共可拥有{girlnum}名舰娘
  您目前没有舰娘。
  发送[大建]
  可以招募舰娘哦。
  
╚                          ╝
'''
        await bot.send(ev, msg, at_sender=True)
    else:
        for cid in cidlist:
            chara_blhxlist.append(chara_blhx.chara_blhx(cid, 0, 0))
        if cidnum <= 7:

            res = chara_blhx.gen_team_pic(chara_blhxlist, star_slot_verbose=False)
        else:
            res1 = chara_blhx.gen_team_pic(chara_blhxlist[:7], star_slot_verbose=False)
            res2 = chara_blhx.gen_team_pic(chara_blhxlist[7:], star_slot_verbose=False)
            res = concat_pic([res1, res2])
        bio = BytesIO()
        res.save(bio, format='PNG')
        base64_str = 'base64://' + base64.b64encode(bio.getvalue()).decode()
        mes = f"[CQ:image,file={base64_str}]"

        msg = f'''
╔                          ╗
  您的等级为{noblename}
  您的红尖尖为{score}
  您共可拥有{girlnum}名舰娘
  您已拥有{cidnum}名舰娘
  她们是：
    {mes}   
╚                          ╝
'''
        await bot.send(ev, msg, at_sender=True)


@sv.on_fullmatch(['招募舰娘', '大建'])
async def add_girl(bot, ev: CQEvent):
    gid = ev.group_id
    uid = ev.user_id
    duel = DuelCounter()
    score_counter = ScoreCounter2()

    if duel._get_level(gid, uid) == 0:
        msg = '您还未在本群创建过指挥官，请发送 创建指挥官 开始您的指挥官之旅。'
        duel_judger.turn_off(ev.group_id)

        await bot.send(ev, msg, at_sender=True)
        return
    else:
        # 防止舰娘数超过上限
        level = duel._get_level(gid, uid)
        noblename = get_noblename(level)
        girlnum = get_girlnum(level)
        cidlist = duel._get_cards(gid, uid)
        cidnum = len(cidlist)
        if cidnum >= girlnum:
            msg = '您的舰娘已经满了哦，快点发送[升级指挥官]进行升级吧。'
            await bot.send(ev, msg, at_sender=True)
            return
        score = score_counter._get_score(gid, uid)
        if score < {GACHA_COST}:
            msg = '您的红尖尖不足{GACHA_COST}哦。'
            await bot.send(ev, msg, at_sender=True)
            return
        newgirllist = get_newgirl_list(gid)
        # 判断舰娘是否被抢没
        if len(newgirllist) == 0:
            await bot.send(ev, '这个群已经没有可以约到的新舰娘了哦。', at_sender=True)
            return
        score_counter._reduce_score(gid, uid, {GACHA_COST})

        # 招募舰娘失败
        if random.random() < 0.4:
            losetext = random.choice(Addgirlfail)
            msg = f'\n{losetext}\n您花费了{GACHA_COST}红尖尖，但是没有约到新的舰娘。'
            await bot.send(ev, msg, at_sender=True)
            return

        # 招募舰娘成功
        cid = random.choice(newgirllist)

        duel._add_card(gid, uid, cid)
        c = chara_blhx.fromid(cid)
        wintext = random.choice(Addgirlsuccess)
        msg = f'\n{wintext}\n招募舰娘成功！\n您花费了300红尖尖\n新招募的舰娘为：{c.name}{c.icon.cqcode}'
        await bot.send(ev, msg, at_sender=True)


@sv.on_fullmatch(['升级等级', '升级指挥官'])
async def add_girl(bot, ev: CQEvent):
    gid = ev.group_id
    uid = ev.user_id
    duel = DuelCounter()
    score_counter = ScoreCounter2()
    score = score_counter._get_score(gid, uid)
    level = duel._get_level(gid, uid)
    noblename = get_noblename(level)
    girlnum = get_girlnum(level)
    cidlist = duel._get_cards(gid, uid)
    cidnum = len(cidlist)

    if level == 6:
        msg = f'您已经是最高等级{noblename}了，不能再升级了。'
        await bot.send(ev, msg, at_sender=True)
        return

    if cidnum < girlnum:
        msg = f'您的舰娘没满哦。\n需要达到{girlnum}名舰娘\n您现在有{cidnum}名。'
        await bot.send(ev, msg, at_sender=True)
        return
    needscore = get_noblescore(level + 1)
    futurename = get_noblename(level + 1)

    if score < needscore:
        msg = f'您的红尖尖不足哦。\n升级到{futurename}需要{needscore}红尖尖'
        await bot.send(ev, msg, at_sender=True)
        return
    score_counter._reduce_score(gid, uid, needscore)
    duel._add_level(gid, uid)
    newlevel = duel._get_level(gid, uid)
    newnoblename = get_noblename(newlevel)
    newgirlnum = get_girlnum(newlevel)
    msg = f'花费了{needscore}红尖尖\n您成功由{noblename}升到了{newnoblename}\n可以拥有{newgirlnum}名舰娘了哦。'
    await bot.send(ev, msg, at_sender=True)


@sv.on_prefix('指挥官决斗')
async def nobleduel(bot, ev: CQEvent):
    if ev.message[0].type == 'at':
        id2 = int(ev.message[0].data['qq'])
    else:
        await bot.finish(ev, '参数格式错误, 请重试')
    if duel_judger.get_on_off_status(ev.group_id):
        await bot.send(ev, "此轮决斗还没结束，请勿重复使用指令。")
        return
    gid = ev.group_id
    duel_judger.turn_on(gid)
    id1 = ev.user_id
    duel = DuelCounter()

    if duel._get_level(gid, id1) == 0:
        msg = f'[CQ:at,qq={id1}]决斗发起者还未在创建过指挥官\n请发送 创建指挥官 开始您的指挥官之旅。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return
    if duel._get_cards(gid, id1) == {}:
        msg = f'[CQ:at,qq={id1}]您没有舰娘，不能参与决斗哦。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return

    if duel._get_level(gid, id2) == 0:
        msg = f'[CQ:at,qq={id2}]被决斗者还未在本群创建过指挥官\n请发送 创建指挥官 开始您的指挥官之旅。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return
    if duel._get_cards(gid, id2) == {}:
        msg = f'[CQ:at,qq={id2}]您没有舰娘，不能参与决斗哦。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return

        # 判定双方的舰娘是否已经超过上限
    level_1 = duel._get_level(gid, id1)
    noblename_1 = get_noblename(level_1)
    girlnum_1 = get_girlnum(level_1)
    cidlist_1 = duel._get_cards(gid, id1)
    cidnum_1 = len(cidlist_1)
    # 这里设定大于才会提醒，就是可以超上限1名，可以自己改成大于等于。
    if cidnum_1 > girlnum_1:
        msg = f'[CQ:at,qq={id1}]您的舰娘超过了等级上限，先去升级等级吧。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return
    level_2 = duel._get_level(gid, id2)
    noblename_2 = get_noblename(level_2)
    girlnum_2 = get_girlnum(level_2)
    cidlist_2 = duel._get_cards(gid, id2)
    cidnum_2 = len(cidlist_2)
    if cidnum_2 > girlnum_2:
        msg = f'[CQ:at,qq={id2}]您的舰娘超过了等级上限，先去升级等级吧。'
        duel_judger.turn_off(ev.group_id)
        await bot.send(ev, msg)
        return

    duel_judger.init_isaccept(gid)
    duel_judger.set_duelid(gid, id1, id2)
    duel_judger.turn_on_accept(gid)
    msg = f'[CQ:at,qq={id2}]对方向您发起了指挥官决斗，请在{WAIT_TIME}秒内[接受/拒绝]。'
    await bot.send(ev, msg)

    await asyncio.sleep(WAIT_TIME)
    duel_judger.turn_off_accept(gid)
    if duel_judger.get_isaccept(gid) is False:
        msg = '决斗被拒绝。'
        await bot.send(ev, msg, at_sender=True)
        duel_judger.turn_off(gid)
        return
    duel = DuelCounter()
    level1 = duel._get_level(gid, id1)
    noblename1 = get_noblename(level1)
    level2 = duel._get_level(gid, id2)
    noblename2 = get_noblename(level2)
    msg = f'''对方接受了决斗！    
1号：[CQ:at,qq={id1}]
等级为：{noblename1}
2号：[CQ:at,qq={id2}]
等级为：{noblename2}
其他人请在{DUEL_SUPPORT_TIME}秒选择支持的对象。
[支持1/2号xxx红尖尖]'''

    await bot.send(ev, msg)
    duel_judger.turn_on_support(gid)
    await asyncio.sleep(DUEL_SUPPORT_TIME)
    duel_judger.turn_off_support(gid)
    deadnum = random.randint(1, 6)
    duel_judger.set_deadnum(gid, deadnum)
    duel_judger.init_turn(gid)
    duel_judger.turn_on_fire(gid)
    duel_judger.turn_off_hasfired(gid)
    msg = f'支持环节结束，下面请决斗双方轮流[开炮]。\n[CQ:at,qq={id1}]先开枪，30秒未开炮自动认输'

    await bot.send(ev, msg)
    n = 1
    while n <= 6:
        wait_n = 0
        while wait_n < 30:
            if duel_judger.get_on_off_hasfired_status(gid):
                break

            wait_n += 1
            await asyncio.sleep(1)
        if wait_n >= 30:
            # 超时未开枪的胜负判定
            loser = duel_judger.get_duelid(gid)[duel_judger.get_turn(gid) - 1]
            winner = duel_judger.get_duelid(gid)[2 - duel_judger.get_turn(gid)]
            msg = f'[CQ:at,qq={loser}]\n你明智的选择了认输。'
            await bot.send(ev, msg)
            break
        else:
            if n == duel_judger.get_deadnum(gid):
                # 被子弹打到的胜负判定
                loser = duel_judger.get_duelid(gid)[duel_judger.get_turn(gid) - 1]
                winner = duel_judger.get_duelid(gid)[2 - duel_judger.get_turn(gid)]
                msg = f'[CQ:at,qq={loser}]\n砰！你死了。'
                await bot.send(ev, msg)
                break
            else:
                id = duel_judger.get_duelid(gid)[duel_judger.get_turn(gid) - 1]
                id2 = duel_judger.get_duelid(gid)[2 - duel_judger.get_turn(gid)]
                msg = f'[CQ:at,qq={id}]\n砰！松了一口气，你并没有死。\n[CQ:at,qq={id2}]\n轮到你开枪了哦。'
                await bot.send(ev, msg)
                n += 1
                duel_judger.change_turn(gid)
                duel_judger.turn_off_hasfired(gid)
                duel_judger.turn_on_fire(gid)

    cidlist = duel._get_cards(gid, loser)
    selected_girl = random.choice(cidlist)
    duel._delete_card(gid, loser, selected_girl)
    duel._add_card(gid, winner, selected_girl)
    c = chara_blhx.fromid(selected_girl)
    msg = f'[CQ:at,qq={loser}]您输掉了指挥官决斗，您被抢走了舰娘\n{c.name}{c.icon.cqcode}'
    await bot.send(ev, msg)

    # 判定是否掉等级
    level_loser = duel._get_level(gid, loser)
    if level_loser > 1:
        noblename_loser = get_noblename(level_loser)
        girlnum_loser = get_girlnum(level_loser - 1)
        cidlist_loser = duel._get_cards(gid, loser)
        cidnum_loser = len(cidlist_loser)
        if cidnum_loser < girlnum_loser:
            duel._reduce_level(gid, loser)
            new_noblename = get_noblename(level_loser - 1)
            msg = f'[CQ:at,qq={loser}]\n您的舰娘数为{cidnum_loser}名\n小于等级需要的舰娘数{girlnum_loser}名\n您的等级下降了到了{new_noblename}'
            await bot.send(ev, msg)

    # 结算下注红尖尖
    score_counter = ScoreCounter2()
    support = duel_judger.get_support(gid)
    winuid = []
    supportmsg = '红尖尖结算:\n'
    winnum = duel_judger.get_duelnum(gid, winner)

    if support != 0:
        for uid in support:
            support_id = support[uid][0]
            support_score = support[uid][1]
            if support_id == winnum:
                winuid.append(uid)
                winscore = support_score * 2
                score_counter._add_score(gid, uid, winscore)
                supportmsg += f'[CQ:at,qq={uid}]+{winscore}红尖尖\n'
            else:
                score_counter._reduce_score(gid, uid, support_score)
                supportmsg += f'[CQ:at,qq={uid}]-{support_score}红尖尖\n'
    await bot.send(ev, supportmsg)
    duel_judger.set_support(ev.group_id)
    duel_judger.turn_off(ev.group_id)
    return


@sv.on_fullmatch('接受')
async def duelaccept(bot, ev: CQEvent):
    gid = ev.group_id
    if duel_judger.get_on_off_accept_status(gid):
        if ev.user_id == duel_judger.get_duelid(gid)[1]:
            gid = ev.group_id
            msg = '指挥官决斗接受成功，请耐心等待决斗开始。'
            await bot.send(ev, msg, at_sender=True)
            duel_judger.turn_off_accept(gid)
            duel_judger.on_isaccept(gid)
        else:
            print('不是被决斗者')
    else:
        print('现在不在决斗期间')


@sv.on_fullmatch('拒绝')
async def duelrefuse(bot, ev: CQEvent):
    gid = ev.group_id
    if duel_judger.get_on_off_accept_status(gid):
        if ev.user_id == duel_judger.get_duelid(gid)[1]:
            gid = ev.group_id
            msg = '您已拒绝指挥官决斗。'
            await bot.send(ev, msg, at_sender=True)
            duel_judger.turn_off_accept(gid)
            duel_judger.off_isaccept(gid)


@sv.on_fullmatch('开炮')
async def duelfire(bot, ev: CQEvent):
    gid = ev.group_id
    if duel_judger.get_on_off_fire_status(gid):
        if ev.user_id == duel_judger.get_duelid(gid)[duel_judger.get_turn(gid) - 1]:
            duel_judger.turn_on_hasfired(gid)
            duel_judger.turn_off_fire(gid)


@sv.on_rex(r'^支持(1|2)号(\d+)(红尖尖|钻石)$')
async def on_input_duel_score(bot, ev: CQEvent):
    try:
        if duel_judger.get_on_off_support_status(ev.group_id):
            gid = ev.group_id
            uid = ev.user_id

            match = ev['match']
            select_id = int(match.group(1))
            input_score = int(match.group(2))
            print(select_id, input_score)
            score_counter = ScoreCounter2()
            # 若下注该群下注字典不存在则创建
            if duel_judger.get_support(gid) == 0:
                duel_judger.set_support(gid)
            support = duel_judger.get_support(gid)
            # 检查是否重复下注
            if uid in support:
                msg = '您已经支持过了。'
                await bot.send(ev, msg, at_sender=True)
                return
            # 检查是否是决斗人员
            duellist = duel_judger.get_duelid(gid)
            if uid in duellist:
                msg = '决斗参与者不能支持。'
                await bot.send(ev, msg, at_sender=True)
                return

                # 检查红尖尖是否足够下注
            if score_counter._judge_score(gid, uid, input_score) == 0:
                msg = '您的红尖尖不足。'
                await bot.send(ev, msg, at_sender=True)
                return
            else:
                duel_judger.add_support(gid, uid, select_id, input_score)
                msg = f'支持{select_id}号成功。'
                await bot.send(ev, msg, at_sender=True)
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))

    # 以下部分与赛跑的重合，有一个即可，两个插件都装建议注释掉。


@sv.on_prefix(['领红尖尖', '领取红尖尖'])
async def add_score(bot, ev: CQEvent):
    try:
        score_counter = ScoreCounter2()
        gid = ev.group_id
        uid = ev.user_id

        current_score = score_counter._get_score(gid, uid)
        if current_score == 0:
            score_counter._add_score(gid, uid, {ZERO_GET_AMOUNT})
            msg = f'您已领取{ZERO_GET_AMOUNT}红尖尖'
            await bot.send(ev, msg, at_sender=True)
            return
        else:
            msg = '红尖尖为0才能领取哦。'
            await bot.send(ev, msg, at_sender=True)
            return
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))


@sv.on_prefix(['查红尖尖', '查询红尖尖', '查看红尖尖'])
async def get_score(bot, ev: CQEvent):
    try:
        score_counter = ScoreCounter2()
        gid = ev.group_id
        uid = ev.user_id

        current_score = score_counter._get_score(gid, uid)
        msg = f'您的红尖尖为{current_score}'
        await bot.send(ev, msg, at_sender=True)
        return
    except Exception as e:
        await bot.send(ev, '错误:\n' + str(e))


@sv.on_rex(f'^为(\d+)充值(\d+)红尖尖$')
async def cheat_score(bot, ev: CQEvent):
    if not priv.check_priv(ev, priv.SUPERUSER):
        await bot.finish(ev, '只有机器人管理才能使用氪金功能哦。', at_sender=True)
    gid = ev.group_id
    match = ev['match']
    id = int(match.group(1))
    num = int(match.group(2))
    duel = DuelCounter()
    score_counter = ScoreCounter2()
    if duel._get_level(gid, id) == 0:
        await bot.finish(ev, '该用户还未在本群创建指挥官哦。', at_sender=True)
    score_counter._add_score(gid, id, num)
    score = score_counter._get_score(gid, id)
    msg = f'已为[CQ:at,qq={id}]充值{num}红尖尖。\n现在共有{score}红尖尖。'
    await bot.send(ev, msg)


@sv.on_fullmatch('重置决斗')
async def init_duel(bot, ev: CQEvent):
    if not priv.check_priv(ev, priv.ADMIN):
        await bot.finish(ev, '只有群管理才能使用重置决斗哦。', at_sender=True)
    duel_judger.turn_off(ev.group_id)
    msg = '已重置本群决斗状态！'
    await bot.send(ev, msg, at_sender=True)


@sv.on_prefix(['查舰娘', '查询舰娘', '查看舰娘'])
async def search_girl(bot, ev: CQEvent):
    args = ev.message.extract_plain_text().split()
    gid = ev.group_id
    if not args:
        await bot.send(ev, '请输入查舰娘+碧蓝航线角色名。', at_sender=True)
        return
    name = args[0]
    cid = chara_blhx.name2id(name)
    if cid == 1000:
        await bot.send(ev, '请输入正确的碧蓝航线角色名。', at_sender=True)
        return
    duel = DuelCounter()
    owner = duel._get_card_owner(gid, cid)
    c = chara_blhx.fromid(cid)

    if owner == 0:
        await bot.send(ev, f'{c.name}现在还是单身哦，快去约到她吧。', at_sender=True)
        return
    else:
        msg = f'{c.name}现在正在\n[CQ:at,qq={owner}]的身边哦。{c.icon.cqcode}'
        await bot.send(ev, msg)
