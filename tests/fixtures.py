"""纯合成测试数据。没有机场账号；所有代理只指向本机弃用端口。"""
from copy import deepcopy

NAMES = [
    "HK-01", "HongKong2 SS", "🇭🇰 香港 03",
    "TW01", "台灣 02", "Taipei 03",
    "JP-01", "Tokyo2 SS", "🇯🇵 日本 03",
    "SG01", "Singapore2 SS", "獅城 03",
    "US-01", "USA02", "California V2", "🇺🇸 美国 04",
    "KR01", "Incheon V2", "Seoul 03",
    "DE01", "Frankfurt SS", "🇩🇪 德國 03",
    "Australia 01", "Singapore Music 1x", "CA Toronto 2GB", "未知地区线路 01",
]
INFO_NAMES = [
    "剩余流量：100 GB", "剩餘流量：50 GB", "套餐到期：2099-01-01",
    "距离下次重置剩余：21 天", "官网地址：https://example.invalid",
    "Traffic Remaining: 100 GB", "Expire: 2099-01-01",
]
REGIONS = ["香港节点", "台湾节点", "日本节点", "狮城节点", "美国节点", "韩国节点", "德国节点"]


def dummy_nodes(names):
    return [{"name": name, "type": "http", "server": "127.0.0.1", "port": 9} for name in names]


def apply_party_patch(base, patch):
    """仅实现本覆写用到的合并规则，不是可用于任意 Party 文件的渲染器。

    Party 普通数组替换、普通映射递归合并、映射键末尾 ! 表示整体替换。
    测试刻意覆盖旧 rule-providers 的移除和订阅数据不变性。
    """
    result = deepcopy(base)
    for key, value in patch.items():
        if key.endswith("!") and isinstance(value, dict):
            result[key[:-1]] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = apply_party_patch(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
