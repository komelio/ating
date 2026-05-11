#!/usr/bin/env python3
"""Generate placeholder JSON data files."""
import json, os, random
from datetime import datetime

DATA = os.path.join(os.path.dirname(__file__), 'v3-dashboard', 'data')
os.makedirs(DATA, exist_ok=True)

def save(fn, data):
    path = os.path.join(DATA, fn)
    with open(path, 'w') as f:
        json.dump({'updated': datetime.now().isoformat(), 'data': data}, f, ensure_ascii=False, default=str)

save('market.json', [
    {'name':'上证指数','code':'1.000001','price':3372.18,'change_pct':0.35,'volume':35680000000,'high':3380.55,'low':3362.10,'open':3365.21,'prev_close':3360.33},
    {'name':'深证成指','code':'0.399001','price':10895.62,'change_pct':-0.12,'volume':45210000000,'high':10920.33,'low':10850.77,'open':10905.44,'prev_close':10908.71},
    {'name':'创业板指','code':'0.399006','price':2210.45,'change_pct':0.68,'volume':18900000000,'high':2215.80,'low':2195.32,'open':2198.10,'prev_close':2195.50},
])

save('stocks.json', [
    {'code':'0.000858','name':'五粮液','price':92.12,'change_pct':-0.40,'change_amt':-0.37,'volume':12500000,'turnover':1150000000,'high':93.05,'low':91.65,'open':92.80,'prev_close':92.49,'pe':22.5},
    {'code':'1.601088','name':'中国神华','price':45.23,'change_pct':-0.55,'change_amt':-0.25,'volume':8900000,'turnover':402000000,'high':45.68,'low':45.05,'open':45.50,'prev_close':45.48,'pe':10.2},
    {'code':'0.000429','name':'粤高速A','price':12.56,'change_pct':-0.16,'change_amt':-0.02,'volume':3200000,'turnover':40200000,'high':12.62,'low':12.50,'open':12.60,'prev_close':12.58,'pe':15.8},
    {'code':'1.600941','name':'中国移动','price':96.38,'change_pct':0.60,'change_amt':0.58,'volume':5100000,'turnover':491000000,'high':96.80,'low':95.50,'open':95.80,'prev_close':95.80,'pe':14.1},
    {'code':'1.601398','name':'工商银行','price':7.46,'change_pct':0.00,'change_amt':0.00,'volume':45000000,'turnover':335000000,'high':7.50,'low':7.43,'open':7.45,'prev_close':7.46,'pe':6.2},
    {'code':'0.601689','name':'拓普集团','price':66.16,'change_pct':-1.94,'change_amt':-1.31,'volume':2800000,'turnover':185000000,'high':67.80,'low':65.90,'open':67.50,'prev_close':67.47,'pe':35.6},
    {'code':'0.002050','name':'三花智控','price':51.20,'change_pct':-2.46,'change_amt':-1.29,'volume':3500000,'turnover':179000000,'high':52.60,'low':51.00,'open':52.50,'prev_close':52.49,'pe':42.1},
    {'code':'1.600519','name':'贵州茅台','price':1645.00,'change_pct':0.25,'change_amt':4.10,'volume':1100000,'turnover':1800000000,'high':1655.00,'low':1635.00,'open':1640.00,'prev_close':1640.90,'pe':32.8},
    {'code':'1.600900','name':'长江电力','price':28.65,'change_pct':0.10,'change_amt':0.03,'volume':15000000,'turnover':430000000,'high':28.80,'low':28.50,'open':28.55,'prev_close':28.62,'pe':20.5},
    {'code':'1.600436','name':'片仔癀','price':305.20,'change_pct':-0.35,'change_amt':-1.07,'volume':800000,'turnover':244000000,'high':308.00,'low':304.50,'open':306.50,'prev_close':306.27,'pe':55.2},
    {'code':'1.688256','name':'寒武纪','price':665.40,'change_pct':3.20,'change_amt':20.64,'volume':5200000,'turnover':3460000000,'high':672.00,'low':640.00,'open':644.76,'prev_close':644.76,'pe':-1},
    {'code':'0.300308','name':'中际旭创','price':132.50,'change_pct':2.10,'change_amt':2.72,'volume':6200000,'turnover':821000000,'high':133.80,'low':130.00,'open':129.78,'prev_close':129.78,'pe':48.5},
    {'code':'1.688041','name':'海光信息','price':98.35,'change_pct':1.50,'change_amt':1.45,'volume':4500000,'turnover':442000000,'high':99.20,'low':97.00,'open':96.90,'prev_close':96.90,'pe':120.5},
    {'code':'1.600406','name':'国电南瑞','price':28.90,'change_pct':-0.25,'change_amt':-0.07,'volume':6200000,'turnover':179000000,'high':29.15,'low':28.75,'open':28.97,'prev_close':28.97,'pe':28.3},
    {'code':'0.000400','name':'许继电气','price':32.15,'change_pct':-0.80,'change_amt':-0.26,'volume':3500000,'turnover':112000000,'high':32.60,'low':31.90,'open':32.41,'prev_close':32.41,'pe':22.8},
    {'code':'1.600391','name':'航天晨光','price':18.25,'change_pct':0.55,'change_amt':0.10,'volume':1800000,'turnover':32800000,'high':18.45,'low':18.05,'open':18.15,'prev_close':18.15,'pe':55.0},
    {'code':'0.003031','name':'江顺科技','price':35.20,'change_pct':-1.20,'change_amt':-0.43,'volume':1200000,'turnover':42200000,'high':35.80,'low':34.90,'open':35.63,'prev_close':35.63,'pe':38.5},
    {'code':'0.002594','name':'比亚迪','price':285.50,'change_pct':1.80,'change_amt':5.05,'volume':8200000,'turnover':2340000000,'high':287.80,'low':280.20,'open':281.00,'prev_close':280.45,'pe':32.1},
])

save('portfolio.json', {
    'cash':49289,
    'holdings':[
        {'name':'五粮液','shares':100,'cost_price':92.49,'current_price':92.12,'category':'现金牛'},
        {'name':'拓普集团','shares':100,'cost_price':67.47,'current_price':66.16,'category':'成长股'},
        {'name':'三花智控','shares':100,'cost_price':52.49,'current_price':51.20,'category':'成长股'},
        {'name':'中国神华','shares':200,'cost_price':45.48,'current_price':45.23,'category':'现金牛'},
        {'name':'粤高速A','shares':500,'cost_price':12.58,'current_price':12.56,'category':'现金牛'},
        {'name':'工商银行','shares':600,'cost_price':7.46,'current_price':7.46,'category':'现金牛'},
        {'name':'中国移动','shares':100,'cost_price':95.80,'current_price':96.38,'category':'现金牛'},
    ]
})

save('news.json', [
    {'title':'梁文锋出资200亿！DeepSeek首轮创纪录融资500亿，V4.1定档6月','source':'量子位','url':'#','category':'国内AI','published_at':'2026-05-09'},
    {'title':'马斯克vs OpenAI庭审第二周：前CTO Murati称无法信任Altman','source':'The Verge','url':'#','category':'AI行业','published_at':'2026-05-09'},
    {'title':'百度发布文心5.1：搜索能力登顶国内，预训练成本仅为业界6%','source':'量子位','url':'#','category':'国内AI','published_at':'2026-05-09'},
    {'title':'阶跃星辰最新语音模型位列评测榜中国第一','source':'量子位','url':'#','category':'国内AI','published_at':'2026-05-09'},
    {'title':'Redis之父下场，给DeepSeek V4单独造了一台推理引擎','source':'量子位','url':'#','category':'开源','published_at':'2026-05-08'},
    {'title':'Nvidia今年已承诺400亿美元AI股权投资','source':'TechCrunch','url':'#','category':'硬件','published_at':'2026-05-08'},
    {'title':'GPT-5级推理能力塞进语音模型，OpenAI同传翻译成本砍穿地板价','source':'量子位','url':'#','category':'模型','published_at':'2026-05-08'},
    {'title':'Anthropic出手！AI的内心独白曝光了','source':'量子位','url':'#','category':'安全','published_at':'2026-05-07'},
    {'title':'所有实验室都怕字节，所有人都在夸DeepSeek','source':'量子位','url':'#','category':'国内AI','published_at':'2026-05-06'},
    {'title':'微软内部邮件曝光：曾担心OpenAI跑去亚马逊并诋毁Azure','source':'The Verge','url':'#','category':'AI行业','published_at':'2026-05-08'},
])

snaps = [{'snapshot_at':datetime(2026,5,11,9,30).isoformat(),'total_asset':99800+random.randint(-200,200),'total_profit':-200+random.randint(-200,200),'cash_cow_pct':38.7,'growth_pct':12.0} for i in range(20)]
save('snapshots.json', snaps)

hist = []
for i in range(20):
    ts = datetime(2026,5,11,9,30).isoformat()
    hist.append({'fetched_at':ts,'name':'上证指数','price':3370+random.randint(-10,10),'change_pct':random.uniform(-0.3,0.3)})
    hist.append({'fetched_at':ts,'name':'深证成指','price':10890+random.randint(-20,20),'change_pct':random.uniform(-0.5,0.5)})
    hist.append({'fetched_at':ts,'name':'创业板指','price':2205+random.randint(-15,15),'change_pct':random.uniform(-0.8,0.8)})
save('history.json', hist)

save('analysis.json', [
    {'session_type':'morning_watch','market_state':'shock','created_at':datetime(2026,5,11,9,40).isoformat(),
     'signals':'["⚠️ 三花智控 单日跌2.5%","⚠️ 拓普集团 单日跌1.9%","🟢 中国移动 逆势+0.6%"]',
     'decisions':'{"reasoning":"早盘低开震荡，成长股承压。现金牛板块托底稳定，移动/神华逆势翻红。建议持仓不动，关注下午量能变化。若三花跌破50元可考虑止损减持10%。"}','screener_output':''},
    {'session_type':'weekly_scan','market_state':'shock','created_at':datetime(2026,5,9,9,0).isoformat(),
     'signals':'["🔴 工商银行分红率~30%不达标","🟡 片仔癀经营现金流/净利≈0.9"]',
     'decisions':'{"reasoning":"无新增入池。现有池18只核验：15只通过，工商降级观察，江顺暂缓。建议下周一扩量重扫。"}',
     'screener_output':'0只现金牛候选，0只成长股候选。分页受限。'},
])

print('✅ All JSON generated in', DATA)