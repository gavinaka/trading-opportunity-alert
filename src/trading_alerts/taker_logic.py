from __future__ import annotations

from typing import Any


LOGIC_VERSION = "tv_only_taker_v1"

NOTION_EVIDENCE = [
    {
        "title": "2025.10.19 第十八周（第三关） 右侧Taker(15分级别以上2B）稳",
        "url": "https://app.notion.com/p/291fda35a09880cfbdc9fa8c0463e015",
        "points": [
            "Taker 优先收敛到 15 分钟级别以上的 2B 右侧进场。",
            "历史记录显示左侧 Taker 样本极差，其余非 2B 机会不应泛化。",
        ],
    },
    {
        "title": "2026.7.2 交易Plan 主账户",
        "url": "https://app.notion.com/p/391fda35a0988007889ae75f7c0e31a9",
        "points": [
            "关键压力附近等待假突破或收割流动性行为，禁止追多。",
            "多空暂时平衡、燃料堆积时，Taker 应等待价格行为确认。",
        ],
    },
]

TRADING_SYSTEM_EVIDENCE = [
    {
        "path": "execution/taker_history.md",
        "points": [
            "Taker 是市价吃单方式，不等于独立账户；独立 Taker 账户历史上已暂停。",
            "历史 Taker 要求至少两次流动性猎杀确认、短线为主、需要实时盯盘。",
        ],
    },
    {
        "path": "execution/entry_models.md",
        "points": [
            "右侧入场必须等待价格行为确认后入场。",
            "右侧适用于趋势延续或结构突破确认，短线为主，通常一次入场。",
        ],
    },
    {
        "path": "scoring/chart_methodology.md",
        "points": [
            "流动性猎杀不能只凭插针预判反转，必须由整体结构与关键位是否守住共同确认。",
            "结构性流动性位置来自各周期摆动高低点、VRVP、VAH、VAL、POC 与共振区。",
        ],
    },
    {
        "path": "constitution/cannot_do_mapping.md",
        "points": [
            "追多/追空只禁止右侧追单，关键是避免在行情延伸末端顺势追价。",
        ],
    },
]

SIGNAL_PLAYBOOK: dict[str, dict[str, Any]] = {
    "breakout_confirm": {
        "name": "突破确认",
        "core": "关键共振支撑/压力区被有效接受后的右侧确认，不是第一根冲破就追。",
        "must_have": [
            "TV 告警必须给出关键位或区间来源。",
            "突破后至少有收盘接受、回踩不失守或连续推进中的一种确认。",
            "入场价距离失效价可控，不能因确认过晚导致止损过宽。",
        ],
        "reject_if": [
            "只是一根插针或单根瞬时拉破。",
            "突破发生在远离 POC/关键区的延伸末端。",
            "取消价、失效价或止损价无法明确。",
        ],
    },
    "false_breakout": {
        "name": "假突破",
        "core": "上破关键压力或前高后无法接受，重新跌回区间，做空候选。",
        "must_have": [
            "上方关键压力、前高或流动性位置明确。",
            "突破失败后重新收回关键位下方。",
            "止损应放在假突破极点上方，取消条件必须明确。",
        ],
        "reject_if": [
            "只是横盘噪音，没有明确前高或压力区。",
            "价格已重新站稳突破区上方。",
            "向下空间不足以覆盖至少 1:2 的计划盈亏比。",
        ],
    },
    "false_breakdown": {
        "name": "假跌破",
        "core": "跌破关键支撑或前低后无法延续，重新收回区间，做多候选。",
        "must_have": [
            "下方关键支撑、前低或流动性位置明确。",
            "跌破失败后重新收回关键位上方。",
            "止损应放在假跌破极点下方，取消条件必须明确。",
        ],
        "reject_if": [
            "只是弱反弹，没有重新收回关键位。",
            "价格已重新跌回破位区下方。",
            "向上空间不足以覆盖至少 1:2 的计划盈亏比。",
        ],
    },
    "liquidity_sweep_reversal": {
        "name": "流动性猎杀反转",
        "core": "扫掉关键高低点流动性后收回，方向由整体结构确认，不能只凭插针做反转。",
        "must_have": [
            "被扫位置必须是明确的前高/前低、摆动高低点或共振区。",
            "扫流动性后出现快速收回或二次确认。",
            "失效价必须贴近扫流动性的极点之外。",
        ],
        "reject_if": [
            "未说明被扫的是哪一级别、哪一个高低点。",
            "扫完后没有收回，也没有结构确认。",
            "单凭长影线推断反转。",
        ],
    },
    "two_b_reversal": {
        "name": "2B反转",
        "core": "15m 以上级别的右侧 2B：突破前高/前低失败并快速收回，用失败突破确认反向机会。",
        "must_have": [
            "时间周期必须不低于 15m。",
            "必须先有清晰的前高/前低或关键区间边界。",
            "价格必须短暂越过该位并失败，随后重新收回关键位内侧。",
            "入场必须是右侧确认，不能提前左侧猜顶/猜底。",
            "止损放在 2B 极点之外，取消价和失效条件必须明确。",
        ],
        "reject_if": [
            "低于 15m 级别。",
            "没有明确前高/前低，只是普通震荡。",
            "收回不成立或再次接受在突破方向。",
            "入场已经变成延伸末端追价。",
        ],
    },
}


def taker_logic_payload() -> dict[str, Any]:
    return {
        "logic_version": LOGIC_VERSION,
        "data_policy": {
            "primary_data": "TradingView webhook event with manually prepared daily key-level context",
            "automatic_external_capture": False,
            "reason": "Taker 机会时效短，早盘人工预设关键位，盘中只等待 TV 价格行为触发。",
        },
        "notion_evidence": NOTION_EVIDENCE,
        "trading_system_evidence": TRADING_SYSTEM_EVIDENCE,
        "signal_playbook": SIGNAL_PLAYBOOK,
        "hard_rules": [
            "TV 告警只是候选，不是交易信号。",
            "正式 Telegram Taker 预警必须满足置信度阈值、风控字段、失效价、取消条件。",
            "禁止用单根 K 线、单一插针或单一变量直接得出交易结论。",
            "禁止在 Trading-System 原工作流内写入或修改任何内容。",
        ],
    }
