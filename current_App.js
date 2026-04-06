import { useEffect, useState, useRef, useCallback } from "react";

const LW_CDN='https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js';
function loadScript(src){return new Promise((res,rej)=>{if(document.querySelector(`script[src="${src}"]`)){res();return;}const s=document.createElement('script');s.src=src;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}

const AI_CONFIG={
  anthropic:{url:'https://api.anthropic.com/v1/messages',model:'claude-sonnet-4-20250514',key:null,label:'Claude Sonnet 4',color:'#f5a623'},
  groq:{url:'https://api.groq.com/openai/v1/chat/completions',model:'llama-3.3-70b-versatile',key:'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',label:'Groq Llama 3.3',color:'#f55036'},
};
const VALLEY_KEY='live_264966be983d94d76527a76199bf85182a69e3b19a918159';

const VALLEY_BASE='https://api.valleyafrica.com/v1';
const COINGECKO='https://api.coingecko.com/api/v3';
const FOREX_API='https://api.frankfurter.app/latest?from=USD&to=GHS,NGN,ZAR,KES,EGP,XOF,EUR,GBP';
const FEAR_API='https://api.alternative.me/fng/?limit=1';

const EXCHANGES={
  GSE:{name:'Ghana Stock Exchange',country:'Ghana',currency:'GHS',flag:'GH',color:'#f5a623'},
  NGX:{name:'Nigerian Exchange Group',country:'Nigeria',currency:'NGN',flag:'NG',color:'#00c853'},
  JSE:{name:'Johannesburg Stock Exch.',country:'South Africa',currency:'ZAR',flag:'ZA',color:'#0ea5e9'},
  NSE:{name:'Nairobi Securities Exch.',country:'Kenya',currency:'KES',flag:'KE',color:'#ff6d00'},
  EGX:{name:'Egyptian Exchange',country:'Egypt',currency:'EGP',flag:'EG',color:'#e53935'},
  BRVM:{name:'Bourse Regionale',country:'W. Africa',currency:'XOF',flag:'WA',color:'#a855f7'},
};

const GSE_SEED={MTNGH:1.86,GCB:6.22,NEWGOLD:195.8,CAL:0.91,EGL:3.45,GOIL:2.10,TOTAL:8.75,GGBL:3.92,UNIL:12.40,BOPP:5.80,ETI:0.18,FML:4.80,MECH:2.40};
const ALL_STOCKS={
  GSE:[{t:'MTNGH',n:'MTN Ghana',s:'Telecom',mc:18500},{t:'GCB',n:'GCB Bank',s:'Banking',mc:7440},{t:'NEWGOLD',n:'NewGold ETF',s:'ETF',mc:9780},{t:'GOIL',n:'GOIL Co.',s:'Energy',mc:1260},{t:'TOTAL',n:'TotalEnergies GH',s:'Energy',mc:2625},{t:'GGBL',n:'Guinness GH',s:'Consumer',mc:1176},{t:'UNIL',n:'Unilever GH',s:'Consumer',mc:2232},{t:'CAL',n:'CAL Bank',s:'Banking',mc:546},{t:'EGL',n:'Enterprise Grp',s:'Insurance',mc:1380},{t:'BOPP',n:'Benso Oil Palm',s:'Agric',mc:1044},{t:'FML',n:'Fan Milk',s:'Consumer',mc:720},{t:'MECH',n:'Mechanical Lloyd',s:'Auto',mc:280}].map(s=>({...s,p:GSE_SEED[s.t]||1,pc:GSE_SEED[s.t]||1,v:Math.floor(Math.random()*1500000+100000),ex:'GSE'})),
  NGX:[{t:'DANGCEM',n:'Dangote Cement',s:'Industry',mc:8260000,p:485,pc:470,v:3200000,ex:'NGX'},{t:'MTNN',n:'MTN Nigeria',s:'Telecom',mc:4028000,p:198.5,pc:195,v:8500000,ex:'NGX'},{t:'ZENITHB',n:'Zenith Bank',s:'Banking',mc:1340000,p:42.5,pc:41.8,v:25000000,ex:'NGX'},{t:'GTCO',n:'GTCo Holdings',s:'Banking',mc:1730000,p:58.9,pc:57.2,v:18000000,ex:'NGX'},{t:'SEPLAT',n:'Seplat Energy',s:'Energy',mc:1900000,p:3200,pc:3150,v:450000,ex:'NGX'}],
  JSE:[{t:'NPN',n:'Naspers',s:'Tech',mc:1450000,p:3420,pc:3380,v:1200000,ex:'JSE'},{t:'BHP',n:'BHP Group',s:'Mining',mc:1180000,p:580,pc:572,v:2800000,ex:'JSE'},{t:'GFI',n:'Gold Fields',s:'Mining',mc:188000,p:264,pc:258,v:3600000,ex:'JSE'},{t:'MTN',n:'MTN Group',s:'Telecom',mc:178000,p:98.5,pc:96.8,v:11000000,ex:'JSE'},{t:'SBK',n:'Standard Bank',s:'Banking',mc:385000,p:242,pc:238,v:3800000,ex:'JSE'}],
  NSE:[{t:'SAFCOM',n:'Safaricom',s:'Telecom',mc:740000,p:18.5,pc:18.1,v:32000000,ex:'NSE'},{t:'EQTY',n:'Equity Group',s:'Banking',mc:198000,p:52,pc:50.5,v:8200000,ex:'NSE'},{t:'KCB',n:'KCB Group',s:'Banking',mc:136000,p:42.5,pc:41.75,v:6100000,ex:'NSE'}],
  EGX:[{t:'COMI',n:'CIB Egypt',s:'Banking',mc:54000,p:72.5,pc:70.8,v:12000000,ex:'EGX'},{t:'EGTS',n:'Egyptian Telecom',s:'Telecom',mc:82000,p:38.9,pc:38,v:5600000,ex:'EGX'}],
  BRVM:[{t:'ONTBV',n:'Orange CI',s:'Telecom',mc:750000,p:12500,pc:12200,v:45000,ex:'BRVM'},{t:'ETIASA',n:'Ecobank CI',s:'Banking',mc:440000,p:8800,pc:8600,v:32000,ex:'BRVM'}],
};

const POLITICAL_RISK={
  GH:{country:'Ghana',leader:'John Mahama',party:'NDC',approvalPct:58,riskLevel:'MEDIUM',notes:'IMF program ongoing.',exchangeImpact:'GSE'},
  NG:{country:'Nigeria',leader:'Bola Tinubu',party:'APC',approvalPct:34,riskLevel:'HIGH',notes:'FX unification. Low approval.',exchangeImpact:'NGX'},
  ZA:{country:'South Africa',leader:'Cyril Ramaphosa',party:'ANC/GNU',approvalPct:42,riskLevel:'MEDIUM',notes:'GNU coalition. Load shedding.',exchangeImpact:'JSE'},
  KE:{country:'Kenya',leader:'William Ruto',party:'UDA',approvalPct:29,riskLevel:'HIGH',notes:'IMF reforms. Low approval.',exchangeImpact:'NSE'},
  EG:{country:'Egypt',leader:'Abdel el-Sisi',party:'Independent',approvalPct:65,riskLevel:'MEDIUM',notes:'IMF tranche approved.',exchangeImpact:'EGX'},
  CI:{country:"Cote d'Ivoire",leader:'Alassane Ouattara',party:'RHDP',approvalPct:55,riskLevel:'LOW',notes:'Most stable BRVM anchor.',exchangeImpact:'BRVM'},
};

const SUPPLY_CHAIN={
  MTNGH:{parent:'MTN Group (JSE)',risks:['ECG Load Shedding - HIGH','Huawei US sanctions - HIGH','NCA regulatory action - MEDIUM'],ecgDep:true},
  GGBL:{parent:'Castel/Diageo (France)',risks:['Suez Canal disruption - HIGH','ECG load shedding - HIGH','Cedi devaluation - MEDIUM'],ecgDep:true},
  FML:{parent:'Danone S.A. (Paris)',risks:['ECG load shedding - CRITICAL','Milk powder imports - HIGH','Cedi devaluation - HIGH'],ecgDep:true},
  UNIL:{parent:'Unilever PLC (London)',risks:['Indonesia palm oil ban - HIGH','Suez disruption - HIGH','ECG shedding - MEDIUM'],ecgDep:true},
  GOIL:{parent:'Govt of Ghana/SSNIT',risks:['Oil price spike - HIGH','Cedi devaluation - CRITICAL','Port congestion - HIGH'],ecgDep:false},
  GCB:{parent:'Govt of Ghana/SSNIT',risks:['IMF debt restructuring - HIGH','Cedi devaluation - MEDIUM'],ecgDep:false},
  NEWGOLD:{parent:'World Gold Council',risks:['Gold price volatility - MEDIUM','USD/GHS rate - HIGH'],ecgDep:false},
};

const RISK_EVENTS=[
  {id:1,title:'ECG load shedding - Accra & Kumasi',type:'ECG Load Shedding',severity:'HIGH',source:'ECG',region:'Ghana',time:'2h ago',desc:'Extended dumsor affecting FML, MTNGH, GGBL operations.'},
  {id:2,title:'Cedi weakening - USD/GHS above 15',type:'Cedi Devaluation',severity:'HIGH',source:'BoG',region:'Ghana',time:'4h ago',desc:'GHS under pressure. Import costs rising for consumer stocks.'},
  {id:3,title:'IMF review - Ghana Article IV',type:'IMF Review',severity:'MEDIUM',source:'IMF',region:'Ghana',time:'1d ago',desc:'Quarterly review upcoming. Positive signals from BoG.'},
  {id:4,title:'Bitcoin volatility - 5% swing',type:'Crypto Volatility',severity:'MEDIUM',source:'CoinGecko',region:'Global',time:'30m ago',desc:'BTC showing high volatility. Fear & Greed at extreme fear.'},
  {id:5,title:'Gold price surge - $3,000/oz',type:'Gold Price Surge',severity:'LOW',source:'Bloomberg',region:'Global',time:'6h ago',desc:'Gold above $3000. NEWGOLD ETF likely to benefit.'},
];

async function callAI(messages, systemPrompt, maxTokens=600, stream=false){
  for(const [provider,cfg] of Object.entries(AI_CONFIG)){
    if(provider==='anthropic'&&!cfg.key) continue;
    try{
      let res, text='';
      if(provider==='anthropic'){
        res=await fetch(cfg.url,{method:'POST',headers:{'Content-Type':'application/json','x-api-key':cfg.key,'anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},body:JSON.stringify({model:cfg.model,max_tokens:maxTokens,system:systemPrompt,messages})});
        const d=await res.json(); text=d.content?.[0]?.text||'No response';
      } else {
        res=await fetch(cfg.url,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${cfg.key}`},body:JSON.stringify({model:cfg.model,max_tokens:maxTokens,messages:[{role:'system',content:systemPrompt},...messages]})});
        const d=await res.json(); text=d.choices?.[0]?.message?.content||'No response';
      }
      return {text,provider,label:cfg.label,color:cfg.color};
    }catch(e){continue;}
  }
  return {text:'AI unavailable. Check connection.',provider:'none',label:'Offline',color:'#4a6a88'};
}

function generateOHLC(seed,days=60){
  const data=[];let p=seed;
  for(let i=days;i>=0;i--){
    const t=Math.floor((Date.now()-i*86400000)/1000);
    const o=p,h=p*(1+Math.random()*0.03),l=p*(1-Math.random()*0.03),c=l+(h-l)*Math.random();
    data.push({time:t,open:+o.toFixed(4),high:+h.toFixed(4),low:+l.toFixed(4),close:+c.toFixed(4)});
    p=c;
  }
  return data;
}

function generateSignal(closes){
  if(!closes||closes.length<35) return null;
  const rsi=(()=>{const p=14;let g=0,l=0;for(let i=1;i<=p;i++){const d=closes[i]-closes[i-1];d>0?g+=d:l-=d;}let ag=g/p,al=l/p;for(let i=p+1;i<closes.length;i++){const d=closes[i]-closes[i-1];ag=(ag*(p-1)+(d>0?d:0))/p;al=(al*(p-1)+(d<0?-d:0))/p;}return al===0?100:+(100-100/(1+ag/al)).toFixed(2);})();
  const ema=(arr,n)=>{if(arr.length<n)return[];const k=2/(n+1);let r=[arr.slice(0,n).reduce((a,b)=>a+b,0)/n];for(let i=n;i<arr.length;i++)r.push(arr[i]*k+r[r.length-1]*(1-k));return r;};
  const e9=ema(closes,9),e21=ema(closes,21);
  const macdLine=ema(closes,12).map((v,i)=>v-(ema(closes,26)[i]||v)).filter(Boolean);
  const hist=macdLine.length>9?macdLine[macdLine.length-1]-(ema(macdLine,9)[ema(macdLine,9).length-1]||0):0;
  const sl=closes.slice(-20),mid=sl.reduce((a,b)=>a+b,0)/20,std=Math.sqrt(sl.reduce((a,b)=>a+(b-mid)**2,0)/20);
  const pctB=(closes[closes.length-1]-mid+2*std)/(4*std);
  let buy=0,sell=0,reasons=[];
  if(rsi<30){buy+=35;reasons.push('RSI oversold');}else if(rsi>70){sell+=35;reasons.push('RSI overbought');}
  if(hist>0){buy+=25;reasons.push('MACD bullish');}else{sell+=25;reasons.push('MACD bearish');}
  if(pctB<0.1){buy+=20;reasons.push('Lower BB bounce');}else if(pctB>0.9){sell+=20;reasons.push('Upper BB rejection');}
  if(e9.length&&e21.length&&e9[e9.length-1]>e21[e21.length-1]){buy+=20;reasons.push('EMA bullish');}else{sell+=20;reasons.push('EMA bearish');}
  const conf=Math.max(buy,sell);
  const signal=buy>sell&&buy>=40?'BUY':sell>buy&&sell>=40?'SELL':'HOLD';
  return {signal,confidence:conf,rsi,macd:+hist.toFixed(4),pctB:+pctB.toFixed(3),reasons:reasons.slice(0,3),sl:+(closes[closes.length-1]*0.97).toFixed(4),tp:+(closes[closes.length-1]*1.04).toFixed(4)};
}

export default function App(){
  const [page,setPage]=useState('dashboard');
  const [sidebarOpen,setSidebarOpen]=useState(true);
  const [activeEx,setActiveEx]=useState('GSE');
  const [stocks,setStocks]=useState(ALL_STOCKS);
  const [selStock,setSelStock]=useState(ALL_STOCKS.GSE[0]);
  const [forex,setForex]=useState({GHS:15.27,NGN:1580,ZAR:18.4,KES:129,EGP:48.5,XOF:610,EUR:0.92,GBP:0.79});
  const [crypto,setCrypto]=useState({});
  const [fearGreed,setFearGreed]=useState({value:42,label:'Fear'});
  const [botSig,setBotSig]=useState(null);
  const [botCoin,setBotCoin]=useState('bitcoin');
  const [botRunning,setBotRunning]=useState(false);
  const [botLog,setBotLog]=useState([]);
  const [msgs,setMsgs]=useState([{role:'assistant',content:"ACCRA TERMINAL V16 online - Africa's #1 Financial Intelligence Platform.\n\nCovering 6 exchanges, 85+ stocks, Real-time crypto, Political risk, Supply chain intelligence\n\nAsk me about any African market, stock analysis, or trading signal.",provider:'anthropic',label:'Claude Sonnet 4',color:'#f5a623'}]);
  const [chatInput,setChatInput]=useState('');
  const [chatLoading,setChatLoading]=useState(false);
  const [dismissedRisks,setDismissedRisks]=useState(new Set());
  const [sortK,setSortK]=useState('mc');
  const [sortD,setSortD]=useState(-1);
  const [searchQ,setSearchQ]=useState('');
  const [cmdSearch,setCmdSearch]=useState('');
  const [showCmd,setShowCmd]=useState(false);
  const [freedom,setFreedom]=useState({terminal:0,crypto:0,gse:0,hydro:0,btcstack:0});
  const [botStatus,setBotStatus]=useState(null);
  const [botStrategy,setBotStrategy]=useState({mode:'balanced',min_confidence:35,max_open_trades:5,crypto_enabled:true,stocks_enabled:true,hfm_enabled:true,avoid_assets:[],prefer_assets:[],market_condition:'neutral'});
  const [botConnected,setBotConnected]=useState(false);
  const [realBal,setRealBal]=useState(null);
  const [realBalLoading,setRealBalLoading]=useState(false);
  const [aiLoading,setAiLoading]=useState(false);
  const [aiRec,setAiRec]=useState('');
  const [pendingStrategy,setPendingStrategy]=useState(null);
  const [approving,setApproving]=useState(false);
  const [portfolio]=useState([{sym:'BTC',qty:0.012,avg:62000,color:'#f7931a'},{sym:'SOL',qty:2.5,avg:140,color:'#9945ff'},{sym:'MTNGH',qty:1200,avg:1.72,color:'#f5a623'},{sym:'GCB',qty:500,avg:5.80,color:'#00c853'}]);
  const chatEndRef=useRef(null);
  const botRef=useRef(null);
  const cmdRef=useRef(null);

  useEffect(()=>{
    async function f(){
      try{
        const r=await fetch(`${COINGECKO}/simple/price?ids=bitcoin,ethereum,solana,binancecoin&vs_currencies=usd&include_24hr_change=true`);
        setCrypto(await r.json());
      }catch{}
    }
    f();const t=setInterval(f,60000);return()=>clearInterval(t);
  },[]);

  useEffect(()=>{
    async function f(){
      try{
        const r=await fetch(FOREX_API);
        const d=await r.json();
        if(d.rates) setForex(d.rates);
      }catch{}
    }
    f();const t=setInterval(f,300000);return()=>clearInterval(t);
  },[]);

  useEffect(()=>{
    async function f(){
      try{
        const r=await fetch(FEAR_API);
        const d=await r.json();
        if(d.data?.[0]) setFearGreed({value:+d.data[0].value,label:d.data[0].value_classification});
      }catch{}
    }
    f();const t=setInterval(f,3600000);return()=>clearInterval(t);
  },[]);

  useEffect(()=>{
    async function f(){
      try{
        const r=await fetch(`${VALLEY_BASE}/stocks/prices`,{headers:{'X-API-Key':VALLEY_KEY}});
        if(!r.ok) return;
        const d=await r.json();
        if(d.data){
          setStocks(prev=>({...prev,GSE:prev.GSE.map(s=>{const live=d.data.find(x=>x.ticker===s.t);return live?{...s,p:live.price||s.p,pc:live.prev_close||s.pc,v:live.volume||s.v}:s;})}));
        }
      }catch{}
    }
    f();const t=setInterval(f,60000);return()=>clearInterval(t);
  },[]);

  const runBot=useCallback(async()=>{
    try{
      const r=await fetch(`${COINGECKO}/coins/${botCoin}/ohlc?vs_currency=usd&days=14`);
      const raw=await r.json();
      if(!Array.isArray(raw)||raw.length<40) return;
      const closes=raw.map(([,,,,c])=>c);
      const price=closes[closes.length-1];
      const sig=generateSignal(closes);
      setBotSig({...sig,price,coin:botCoin});
      setBotLog(prev=>[{time:new Date().toLocaleTimeString(),coin:botCoin.toUpperCase(),price,action:sig.signal,confidence:sig.confidence,rsi:sig.rsi,macd:sig.macd,reasons:sig.reasons?.[0]||''},...prev.slice(0,14)]);
    }catch{}
  },[botCoin]);

  useEffect(()=>{if(botRunning){runBot();botRef.current=setInterval(runBot,30000);}else clearInterval(botRef.current);return()=>clearInterval(botRef.current);},[botRunning,runBot]);

    useEffect(()=>{
    async function fetchBotStatus(){
      try{
        const r=await fetch(`https://gist.githubusercontent.com/nanabenyin0246-dev/4f5f6918288ddaec0a1fc998af3e6f99/raw/bot_status.json?t=${Date.now()}`,{cache:'no-store'});
        if(r.ok){const d=await r.json();setBotStatus(d);setBotConnected(true);}
        else{setBotConnected(false);}
      }catch{setBotConnected(false);}
    }
    fetchBotStatus();
    const t=setInterval(fetchBotStatus,60000);
    return()=>clearInterval(t);
  },[]);

  async function pushStrategy(newStrategy){
    try{
      const updated={...botStrategy,...newStrategy,last_updated:new Date().toISOString(),updated_by:'terminal_ai'};
      setBotStrategy(updated);
      await sendChat('Based on current market conditions analyze and confirm this strategy change: '+JSON.stringify(newStrategy));
    }catch(e){console.error(e);}
  }
  async function fetchRealBal(){
    setRealBalLoading(true);
    try{
      const resp=await fetch('https://api.binance.com/api/v3/ticker/24hr',{cache:'no-store'});
      const tickers=await resp.json();
      const prices={};
      tickers.forEach(t=>{if(t.symbol.endsWith('USDT'))prices[t.symbol.replace('USDT','')]=parseFloat(t.lastPrice);});
      const sol=prices['SOL']||0,btc=prices['BTC']||0,eth=prices['ETH']||0;
      setRealBal({sol_price:sol,btc_price:btc,eth_price:eth,
        sol_value:(0.2897*sol).toFixed(2),usdt:27.42,
        total:(27.42+0.2897*sol).toFixed(2),
        pnl_pct:(((27.42+0.2897*sol)-48)/48*100).toFixed(1),
        updated:new Date().toLocaleTimeString()});
    }catch(e){console.error(e);}
    setRealBalLoading(false);
  }
  async function approveStrategy(strategy){
    setApproving(true);
    try{
      const payload={files:{'bot_strategy.json':{content:JSON.stringify({
        ...strategy,
        last_updated:new Date().toISOString(),
        updated_by:'terminal_ai'
      },null,2)}}};
      await fetch('https://api.github.com/gists/4f5f6918288ddaec0a1fc998af3e6f99',{
        method:'PATCH',
        headers:{'Authorization':'Bearer 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','Content-Type':'application/json'},
        body:JSON.stringify(payload)});
      setBotStrategy(prev=>({...prev,...strategy}));
      setPendingStrategy(null);
      setAiRec('Strategy approved and sent to bot! Changes will take effect next cycle.');
    }catch(e){setAiRec('Failed to send strategy to bot. Try again.');}
    setApproving(false);
  }

  async function sendChat(text){
    const msg=text||chatInput.trim();if(!msg||chatLoading)return;
    setMsgs(prev=>[...prev,{role:'user',content:msg}]);setChatInput('');setChatLoading(true);
    const gse=stocks.GSE?.slice(0,4).map(s=>`${s.t}:GHS${s.p}(${((s.p-s.pc)/s.pc*100)>0?'+':''}${((s.p-s.pc)/s.pc*100).toFixed(1)}%)`).join(',');
    const sysPrompt=`You are ACCRA, AI analyst for Accra Terminal V16 - Africa's #1 financial intelligence platform. 6 exchanges: GSE,NGX,JSE,NSE,EGX,BRVM. Live: BTC=$${crypto.bitcoin?.usd?.toLocaleString()||'N/A'}, ETH=$${crypto.ethereum?.usd?.toLocaleString()||'N/A'}, USD/GHS=${forex.GHS?.toFixed(2)||'N/A'}, F&G:${fearGreed?.value||'N/A'}. GSE: ${gse||'loading'}. Political: Ghana(Mahama,58%),Nigeria(Tinubu,34%-HIGH),Kenya(Ruto,29%-HIGH). Active risks: ECG load shedding, GHS weakening. Be concise, data-driven, Africa-specific.`;
    const history=msgs.filter(m=>m.role!=='system').slice(-6).map(m=>({role:m.role,content:m.content}));
    history.push({role:'user',content:msg});
    const result=await callAI(history,sysPrompt,600,false);
    setMsgs(prev=>[...prev,{role:'assistant',content:result.text,provider:result.provider,label:result.label,color:result.color}]);
    setChatLoading(false);
  }

  useEffect(()=>{chatEndRef.current?.scrollIntoView({behavior:'smooth'});},[msgs]);

  const criticalRisks=RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)&&e.severity==='HIGH').length;
  const fV=v=>v==null||isNaN(v)?'--':v>=1e6?`${(v/1e6).toFixed(1)}M`:v>=1e3?`${(v/1000).toFixed(0)}K`:String(v);
  const pc=v=>v==null||isNaN(v)?'#888':v>0?'#00e676':v<0?'#ff1744':'#888';
  const fP=v=>v==null||isNaN(v)?'0.00%':`${v>0?'+':''}${v.toFixed(2)}%`;
  const sevC=s=>s==='CRITICAL'?'#ff1744':s==='HIGH'?'#ff6d00':s==='MEDIUM'?'#ffd600':'#00e676';

  // Bloomberg color system
  const C={
    bg:'#0a0e1a',
    bg2:'#0f1422',
    bg3:'#141928',
    card:'#111827',
    border:'#1e2d47',
    border2:'#243550',
    text:'#e6e6e6',
    text2:'#a0a0a0',
    text3:'#5a6a7a',
    green:'#00e676',
    red:'#ff1744',
    yellow:'#ffd600',
    blue:'#2196f3',
    orange:'#ff6d00',
    gold:'#f5a623',
    accent:'#1565c0',
  };

  const NAV_ITEMS=[
    {id:'dashboard',icon:'D',label:'Dashboard'},
    {id:'markets',icon:'M',label:'Markets'},
    {id:'map',icon:'O',label:'African Map'},
    {id:'portfolio',icon:'P',label:'Portfolio'},
    {id:'risk',icon:'!',label:'Risk Radar',badge:criticalRisks||null},
    {id:'crypto',icon:'B',label:'Crypto'},
    {id:'forex',icon:'FX',label:'Forex'},
    {id:'bot',icon:'AI',label:'Bot Signals'},
    {id:'supply',icon:'SC',label:'Supply Chain'},
    {id:'news',icon:'N',label:'News'},
    {id:'ai',icon:'~',label:'AI Assistant'},
    {id:'alerts',icon:'A',label:'Alerts',badge:criticalRisks||null},
    {id:'freedom',icon:'*',label:'My Freedom'},
    {id:'botlive',icon:'B8',label:'Bot Live',badge:botConnected?null:'OFF'},
    {id:'settings',icon:'S',label:'Settings'},
  ];

  const activeStocks=(stocks[activeEx]||[])
    .filter(s=>!searchQ||s.t.toLowerCase().includes(searchQ.toLowerCase())||s.n.toLowerCase().includes(searchQ.toLowerCase()))
    .sort((a,b)=>{
      const av=sortK==='chg'?(a.p-a.pc)/a.pc:a[sortK]||0;
      const bv=sortK==='chg'?(b.p-b.pc)/b.pc:b[sortK]||0;
      return sortD*(bv-av);
    });

  const portfolioValue=portfolio.reduce((sum,h)=>{
    const price=h.sym==='BTC'?crypto.bitcoin?.usd:h.sym==='SOL'?crypto.solana?.usd:h.sym==='MTNGH'?selStock?.p||h.avg:h.avg;
    return sum+(price||h.avg)*h.qty;
  },0);

  // Command search handler
  function handleCmd(q){
    const ql=q.toLowerCase();
    if(['btc','bitcoin'].includes(ql)){setPage('crypto');setShowCmd(false);setCmdSearch('');}
    else if(['eth','ethereum'].includes(ql)){setPage('crypto');setShowCmd(false);setCmdSearch('');}
    else if(['ghs','forex','usdghs'].includes(ql)){setPage('forex');setShowCmd(false);setCmdSearch('');}
    else if(ql==='gse'||ql==='markets'){setPage('markets');setActiveEx('GSE');setShowCmd(false);setCmdSearch('');}
    else if(ql==='news'){setPage('news');setShowCmd(false);setCmdSearch('');}
    else if(ql==='ai'){setPage('ai');setShowCmd(false);setCmdSearch('');}
    else if(ql==='risk'||ql==='alerts'){setPage('alerts');setShowCmd(false);setCmdSearch('');}
    else {
      const found=Object.values(ALL_STOCKS).flat().find(s=>s.t.toLowerCase()===ql||s.n.toLowerCase().includes(ql));
      if(found){setSelStock(found);setActiveEx(found.ex);setPage('markets');setShowCmd(false);setCmdSearch('');}
      else sendChat(q);
    }
  }

  // Styles
  const cardStyle={background:C.card,border:`1px solid ${C.border}`,borderRadius:8,padding:'16px 20px'};
  const headerStyle={fontSize:16,fontWeight:600,color:C.text,marginBottom:12,letterSpacing:0.3};
  const numStyle={fontSize:20,fontWeight:700,color:C.text,letterSpacing:0.3};

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const _G='4f5f6918288ddaec0a1fc998af3e6f99';
    const _T='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';
    const _push=async()=>{
      try{
        const _b=crypto?.bitcoin?.usd_24h_change||0;
        const _f=fearGreed?.value||50;
        const _g=Math.min(100,
          RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)&&e.severity==='HIGH').length*15+
          RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)&&e.severity==='CRITICAL').length*25+
          (forex?.GHS>16?10:forex?.GHS>15?5:0)+(_f<20?5:_f>80?8:0));
        await fetch('https://api.github.com/gists/'+_G,{
          method:'PATCH',
          headers:{'Authorization':'Bearer '+_T,'Content-Type':'application/json'},
          body:JSON.stringify({files:{'terminal_intelligence.json':{content:JSON.stringify({
            timestamp:new Date().toISOString(),
            source:'accra_terminal_v16',
            global_risk_score:_g,
            risk_level:_g>70?'CRITICAL':_g>45?'HIGH':_g>25?'MEDIUM':'LOW',
            crypto:{
              btc_price:crypto?.bitcoin?.usd||0,
              btc_24h_change:_b,
              btc_trend:_b>4?'STRONG_UP':_b>1.5?'UP':_b<-4?'STRONG_DOWN':_b<-1.5?'DOWN':'NEUTRAL',
              eth_price:crypto?.ethereum?.usd||0,
              sol_price:crypto?.solana?.usd||0,
              fear_greed:_f,
              fear_greed_label:fearGreed?.label||'Neutral',
            },
            fx_stress:{
              GHS:{rate:forex?.GHS,trend:forex?.GHS>16?'CRISIS':forex?.GHS>15.5?'WEAK':'STABLE'},
              NGN:{rate:forex?.NGN,trend:forex?.NGN>1700?'CRISIS':forex?.NGN>1600?'WEAK':'STABLE'},
              ZAR:{rate:forex?.ZAR,trend:forex?.ZAR>20?'CRISIS':forex?.ZAR>19?'WEAK':'STABLE'},
            },
            active_risks:RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)).map(e=>({
              title:e.title,severity:e.severity,
              score:e.severity==='CRITICAL'?25:e.severity==='HIGH'?15:8,
              affects_crypto:['war','conflict','sanction','fed','inflation'].some(k=>e.title.toLowerCase().includes(k)),
              affects_gold:['gold','inflation','war','conflict'].some(k=>e.title.toLowerCase().includes(k)),
              affects_oil:['oil','opec','iran','gulf'].some(k=>e.title.toLowerCase().includes(k)),
              affects_african_stocks:['ecg','cedi','naira','imf','ghana','nigeria'].some(k=>e.title.toLowerCase().includes(k)),
            })),
            recommendations:[
              ...(_g>65?[{action:'REDUCE_EXPOSURE',priority:'HIGH'}]:[]),
              ...(_f<=20?[{action:'ACCUMULATE_BTC',priority:'HIGH'}]:[]),
              ...(_f>=85?[{action:'TAKE_PROFITS',priority:'HIGH'}]:[]),
              ...(forex?.GHS>16?[{action:'FAVOR_HARD_ASSETS',priority:'HIGH'}]:[]),
            ],
            quick_signals:{
              mode_suggestion:_g>65?'conservative':_g>35?'balanced':'aggressive',
              btc_favorable:_f<45&&_b>-6,
            },
          })}}}),
        });
      }catch(_e){console.warn('[INTEL]',_e.message);}
    };
    _push();
    const _t=setInterval(_push,300000);
    return()=>clearInterval(_t);
  },[fearGreed,crypto,forex,dismissedRisks]);


  return (
    <div style={{display:'flex',height:'100vh',background:C.bg,color:C.text,fontFamily:"'Inter','IBM Plex Sans',sans-serif",overflow:'hidden',fontSize:14}}>

      {/* COMMAND SEARCH OVERLAY */}
      {showCmd&&(
        <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.7)',zIndex:1000,display:'flex',alignItems:'flex-start',justifyContent:'center',paddingTop:120}}>
          <div style={{...cardStyle,width:560,padding:0,overflow:'hidden',boxShadow:'0 20px 60px rgba(0,0,0,0.8)'}}>
            <div style={{display:'flex',alignItems:'center',padding:'14px 18px',borderBottom:`1px solid ${C.border}`}}>
              <span style={{color:C.text3,marginRight:10,fontSize:16}}>&gt;</span>
              <input ref={cmdRef} value={cmdSearch} onChange={e=>setCmdSearch(e.target.value)}
                onKeyDown={e=>{if(e.key==='Enter')handleCmd(cmdSearch);if(e.key==='Escape'){setShowCmd(false);setCmdSearch('');}}}
                placeholder="Search: BTC, USDGHS, MTNGH, GSE, NEWS..." autoFocus
                style={{flex:1,background:'transparent',border:'none',outline:'none',color:C.text,fontSize:16,fontFamily:'inherit'}}/>
              <span style={{color:C.text3,fontSize:12}}>ESC to close</span>
            </div>
            <div style={{padding:'8px 0'}}>
              {['BTC - Bitcoin','USDGHS - Forex Rate','MTNGH - MTN Ghana','GSE - Markets','NEWS - News Feed','AI - Ask ACCRA'].map(item=>(
                <div key={item} onClick={()=>handleCmd(item.split(' ')[0])}
                  style={{padding:'10px 18px',cursor:'pointer',color:C.text2,fontSize:14,transition:'background 0.15s'}}
                  onMouseEnter={e=>e.currentTarget.style.background=C.bg3}
                  onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SIDEBAR */}
      <div style={{width:sidebarOpen?220:56,background:C.bg2,borderRight:`1px solid ${C.border}`,display:'flex',flexDirection:'column',transition:'width 0.2s',flexShrink:0,overflow:'hidden'}}>
        {/* Logo */}
        <div style={{padding:'16px 12px',borderBottom:`1px solid ${C.border}`,display:'flex',alignItems:'center',gap:10,minHeight:56}}>
          <div style={{width:32,height:32,background:C.gold,borderRadius:6,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:700,fontSize:13,color:'#000',flexShrink:0}}>AT</div>
          {sidebarOpen&&<div>
            <div style={{fontSize:13,fontWeight:700,color:C.gold,letterSpacing:1}}>ACCRA</div>
            <div style={{fontSize:9,color:C.text3,letterSpacing:1}}>TERMINAL V16</div>
          </div>}
          <div style={{marginLeft:'auto',cursor:'pointer',color:C.text3,fontSize:18,flexShrink:0}} onClick={()=>setSidebarOpen(o=>!o)}>{sidebarOpen?'<':'>'}</div>
        </div>

        {/* Status */}
        {sidebarOpen&&<div style={{padding:'8px 14px',borderBottom:`1px solid ${C.border}`}}>
          <div style={{fontSize:10,color:C.green,display:'flex',alignItems:'center',gap:5}}>
            <span style={{width:6,height:6,borderRadius:'50%',background:C.green,display:'inline-block'}}></span>
            Live - Investor Mode
          </div>
        </div>}

        {/* Nav */}
        <div style={{flex:1,overflowY:'auto',padding:'8px 6px'}}>
          {NAV_ITEMS.map(item=>{
            const active=page===item.id;
            return(
              <div key={item.id} onClick={()=>setPage(item.id)}
                style={{display:'flex',alignItems:'center',gap:10,padding:sidebarOpen?'10px 10px':'10px 0',justifyContent:sidebarOpen?'flex-start':'center',cursor:'pointer',borderRadius:6,marginBottom:2,
                  background:active?`${C.gold}18`:'transparent',
                  borderLeft:active?`3px solid ${C.gold}`:'3px solid transparent',
                  color:active?C.gold:C.text2,transition:'all 0.15s'}}
                onMouseEnter={e=>{if(!active){e.currentTarget.style.background=C.bg3;e.currentTarget.style.color=C.text;}}}
                onMouseLeave={e=>{if(!active){e.currentTarget.style.background='transparent';e.currentTarget.style.color=C.text2;}}}>
                <span style={{width:22,height:22,borderRadius:5,background:active?`${C.gold}30`:C.bg3,display:'flex',alignItems:'center',justifyContent:'center',fontSize:10,fontWeight:700,color:active?C.gold:C.text3,flexShrink:0}}>{item.icon}</span>
                {sidebarOpen&&<span style={{fontSize:14,fontWeight:500,whiteSpace:'nowrap'}}>{item.label}</span>}
                {sidebarOpen&&item.badge&&<span style={{marginLeft:'auto',background:C.red,color:'#fff',borderRadius:10,padding:'1px 6px',fontSize:10,fontWeight:700}}>{item.badge}</span>}
              </div>
            );
          })}
        </div>

        {/* Command Search Button */}
        <div style={{padding:'10px 6px',borderTop:`1px solid ${C.border}`}}>
          <div onClick={()=>setShowCmd(true)} style={{display:'flex',alignItems:'center',gap:8,padding:'8px 10px',background:C.bg3,borderRadius:6,cursor:'pointer',border:`1px solid ${C.border}`}}>
            <span style={{color:C.text3,fontSize:12}}>{'>'}</span>
            {sidebarOpen&&<span style={{color:C.text3,fontSize:12}}>Command search...</span>}
          </div>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>

        {/* TOP BAR */}
        <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,padding:'0 20px',height:56,display:'flex',alignItems:'center',gap:16,flexShrink:0}}>
          <div style={{fontSize:18,fontWeight:700,color:C.gold,letterSpacing:0.5,marginRight:8}}>
            {NAV_ITEMS.find(n=>n.id===page)?.label||'Dashboard'}
          </div>

          {/* Intelligence Strip */}
          <div style={{flex:1,display:'flex',gap:8,overflowX:'auto'}}>
            {[
              {label:'Risk Score',val:`${criticalRisks*15+25}/100`,color:criticalRisks>1?C.red:criticalRisks>0?C.orange:C.green,trend:criticalRisks>0?'+':'-'},
              {label:'USD/GHS',val:(forex.GHS||15.27).toFixed(2),color:forex.GHS>15?C.red:C.green,trend:forex.GHS>15?'+':'-'},
              {label:'BTC',val:`$${(crypto.bitcoin?.usd||67240).toLocaleString()}`,color:pc(crypto.bitcoin?.usd_24h_change||0),trend:crypto.bitcoin?.usd_24h_change>0?'+':'-'},
              {label:'ETH',val:`$${(crypto.ethereum?.usd||3240).toLocaleString()}`,color:pc(crypto.ethereum?.usd_24h_change||0),trend:crypto.ethereum?.usd_24h_change>0?'+':'-'},
              {label:'Fear&Greed',val:`${fearGreed?.value||42}`,color:fearGreed?.value<30?C.green:fearGreed?.value>70?C.red:C.yellow,trend:fearGreed?.value<50?'v':'^'},
              {label:'Oil',val:'$82.4',color:C.yellow,trend:'-'},
            ].map(item=>(
              <div key={item.label} style={{display:'flex',flexDirection:'column',padding:'4px 12px',background:C.bg3,borderRadius:5,border:`1px solid ${C.border}`,minWidth:90,flexShrink:0}}>
                <span style={{fontSize:10,color:C.text3,letterSpacing:0.5}}>{item.label}</span>
                <span style={{fontSize:13,fontWeight:700,color:item.color,letterSpacing:0.3}}>{item.trend} {item.val}</span>
              </div>
            ))}
          </div>

          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <div onClick={()=>setShowCmd(true)} style={{padding:'6px 12px',background:C.bg3,border:`1px solid ${C.border}`,borderRadius:5,cursor:'pointer',color:C.text3,fontSize:12}}>Search</div>
            <div style={{width:32,height:32,borderRadius:'50%',background:C.accent,display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,fontWeight:700}}>NB</div>
          </div>
        </div>

        {/* PAGE CONTENT */}
        <div style={{flex:1,overflowY:'auto',padding:20}}>

          {/* â•â•â• DASHBOARD â•â•â• */}
          {page==='dashboard'&&(
            <div>
              {/* 3-column layout */}
              <div style={{display:'grid',gridTemplateColumns:'1fr 1.5fr 1fr',gap:16,marginBottom:16}}>

                {/* LEFT: Markets Table */}
                <div style={cardStyle}>
                  <div style={headerStyle}>Live Markets - GSE</div>
                  <div style={{overflowY:'auto',maxHeight:340}}>
                    <table style={{width:'100%',borderCollapse:'collapse'}}>
                      <thead>
                        <tr style={{borderBottom:`1px solid ${C.border}`}}>
                          {['Ticker','Price','Chg%'].map(h=>(
                            <th key={h} style={{padding:'8px 6px',textAlign:'left',fontSize:11,color:C.text3,fontWeight:600,letterSpacing:0.5}}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(stocks.GSE||[]).map((s,i)=>{
                          const chg=(s.p-s.pc)/s.pc*100;
                          return(
                            <tr key={i} onClick={()=>{setSelStock(s);setPage('markets');}}
                              style={{borderBottom:`1px solid ${C.border}`,cursor:'pointer',transition:'background 0.1s'}}
                              onMouseEnter={e=>e.currentTarget.style.background=C.bg3}
                              onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                              <td style={{padding:'10px 6px',fontWeight:600,color:C.gold,fontSize:13}}>{s.t}</td>
                              <td style={{padding:'10px 6px',fontWeight:700,fontSize:14}}>{(s.p||0).toFixed(2)}</td>
                              <td style={{padding:'10px 6px',color:pc(chg),fontWeight:600,fontSize:13}}>{fP(chg)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* CENTER: Chart + Signal */}
                <div style={{display:'flex',flexDirection:'column',gap:16}}>
                  <div style={cardStyle}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
                      <div style={headerStyle}>{selStock?.t||'MTNGH'} - {selStock?.n||'MTN Ghana'}</div>
                      <div style={{display:'flex',gap:6}}>
                        {['1D','5D','1M','1Y'].map(tf=>(
                          <button key={tf} style={{padding:'3px 10px',background:C.bg3,border:`1px solid ${C.border}`,borderRadius:4,color:C.text2,fontSize:11,cursor:'pointer'}}>{tf}</button>
                        ))}
                      </div>
                    </div>
                    <TradingChart data={generateOHLC(selStock?.p||1.86)} />
                  </div>
                </div>

                {/* RIGHT: AI Decision Engine */}
                <div style={{display:'flex',flexDirection:'column',gap:16}}>
                  <div style={cardStyle}>
                    <div style={headerStyle}>AI Decision Engine</div>
                    {botSig?(
                      <div>
                        <div style={{textAlign:'center',padding:'16px 0',borderBottom:`1px solid ${C.border}`,marginBottom:12}}>
                          <div style={{fontSize:32,fontWeight:700,color:botSig.signal==='BUY'?C.green:botSig.signal==='SELL'?C.red:C.yellow,letterSpacing:2}}>{botSig.signal}</div>
                          <div style={{fontSize:18,fontWeight:600,color:C.text2,marginTop:4}}>{botSig.confidence}% confidence</div>
                        </div>
                        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:12}}>
                          {[['RSI',botSig.rsi],['MACD',botSig.macd],['SL',`$${botSig.sl}`],['TP',`$${botSig.tp}`]].map(([k,v])=>(
                            <div key={k} style={{background:C.bg3,borderRadius:5,padding:'8px 10px',border:`1px solid ${C.border}`}}>
                              <div style={{fontSize:10,color:C.text3}}>{k}</div>
                              <div style={{fontSize:14,fontWeight:700,color:C.text}}>{v}</div>
                            </div>
                          ))}
                        </div>
                        {botSig.reasons?.map((r,i)=><div key={i} style={{fontSize:12,color:C.text2,padding:'3px 0'}}>- {r}</div>)}
                      </div>
                    ):(
                      <div style={{textAlign:'center',padding:24}}>
                        <div style={{fontSize:12,color:C.text3,marginBottom:12}}>Select a coin and start the bot</div>
                        <select value={botCoin} onChange={e=>setBotCoin(e.target.value)} style={{background:C.bg3,border:`1px solid ${C.border}`,color:C.text,padding:'6px 10px',borderRadius:5,marginBottom:10,width:'100%'}}>
                          {[['bitcoin','BTC'],['ethereum','ETH'],['solana','SOL'],['binancecoin','BNB']].map(([v,l])=>(
                            <option key={v} value={v}>{l}</option>
                          ))}
                        </select>
                        <button onClick={()=>setBotRunning(r=>!r)} style={{width:'100%',padding:'10px',background:botRunning?`${C.red}20`:C.gold,border:'none',borderRadius:6,color:botRunning?C.red:'#000',fontWeight:700,fontSize:14,cursor:'pointer'}}>
                          {botRunning?'Stop Bot':'Start Bot'}
                        </button>
                      </div>
                    )}
                    {botSig&&<button onClick={()=>setBotRunning(r=>!r)} style={{width:'100%',marginTop:10,padding:'8px',background:botRunning?`${C.red}20`:C.green+'20',border:`1px solid ${botRunning?C.red:C.green}`,borderRadius:5,color:botRunning?C.red:C.green,fontWeight:600,fontSize:13,cursor:'pointer'}}>
                      {botRunning?'Stop Bot':'Start Bot'}
                    </button>}
                  </div>

                  {/* Quick Alerts */}
                  <div style={cardStyle}>
                    <div style={headerStyle}>Active Alerts</div>
                    {RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)).slice(0,3).map(e=>(
                      <div key={e.id} style={{padding:'8px 0',borderBottom:`1px solid ${C.border}`,display:'flex',gap:8,alignItems:'flex-start'}}>
                        <span style={{color:sevC(e.severity),fontSize:16,marginTop:1}}>!</span>
                        <div style={{flex:1}}>
                          <div style={{fontSize:12,fontWeight:600,color:C.text}}>{e.title}</div>
                          <div style={{fontSize:11,color:C.text3}}>{e.time} - {e.region}</div>
                        </div>
                        <span style={{fontSize:10,color:sevC(e.severity),background:`${sevC(e.severity)}18`,padding:'2px 6px',borderRadius:3,flexShrink:0}}>{e.severity}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Second row */}
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:16}}>
                {/* Portfolio */}
                <div style={cardStyle}>
                  <div style={headerStyle}>Portfolio Overview</div>
                  <div style={{...numStyle,color:C.green,marginBottom:4}}>${portfolioValue.toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2})}</div>
                  <div style={{fontSize:12,color:C.green,marginBottom:16}}>+ 3.42% Today</div>
                  {portfolio.map((h,i)=>{
                    const price=h.sym==='BTC'?crypto.bitcoin?.usd:h.sym==='SOL'?crypto.solana?.usd:h.avg;
                    const val=(price||h.avg)*h.qty;
                    const pnlPct=((price||h.avg)-h.avg)/h.avg*100;
                    return(
                      <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'8px 0',borderBottom:`1px solid ${C.border}`}}>
                        <div style={{display:'flex',alignItems:'center',gap:8}}>
                          <div style={{width:8,height:8,borderRadius:'50%',background:h.color}}></div>
                          <span style={{fontSize:13,fontWeight:600}}>{h.sym}</span>
                        </div>
                        <div style={{textAlign:'right'}}>
                          <div style={{fontSize:13,fontWeight:700}}>${val.toFixed(0)}</div>
                          <div style={{fontSize:11,color:pc(pnlPct)}}>{fP(pnlPct)}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Top News */}
                <div style={cardStyle}>
                  <div style={headerStyle}>Market Intelligence</div>
                  {[
                    {title:'Ghana IMF review on track â€” BoG signals cedi stabilisation',tag:'IMF',color:C.blue,time:'2h ago'},
                    {title:'ECG load shedding extended â€” FML, MTNGH operations affected',tag:'ECG',color:C.red,time:'4h ago'},
                    {title:'Bitcoin fear & greed at 16 â€” extreme fear territory',tag:'Crypto',color:C.yellow,time:'30m ago'},
                    {title:'DANGCEM Q1 results beat expectations â€” NGX rallying',tag:'Earnings',color:C.green,time:'1d ago'},
                    {title:'Gold above $3,000 â€” NEWGOLD ETF outperforms',tag:'Gold',color:C.gold,time:'6h ago'},
                  ].map((n,i)=>(
                    <div key={i} style={{padding:'8px 0',borderBottom:`1px solid ${C.border}`,cursor:'pointer'}} onClick={()=>sendChat(`Tell me more about: ${n.title}`)}>
                      <div style={{display:'flex',gap:6,marginBottom:4}}>
                        <span style={{fontSize:10,color:n.color,background:`${n.color}18`,padding:'2px 6px',borderRadius:3,fontWeight:600}}>{n.tag}</span>
                        <span style={{fontSize:10,color:C.text3}}>{n.time}</span>
                      </div>
                      <div style={{fontSize:13,color:C.text,lineHeight:1.5}}>{n.title}</div>
                    </div>
                  ))}
                </div>

                {/* AI Allocation */}
                <div style={cardStyle}>
                  <div style={headerStyle}>AI Sector Signals</div>
                  {[
                    {label:'Crypto',signal:'CAUTION',color:C.yellow,alloc:20,reason:'Extreme fear zone'},
                    {label:'African Stocks',signal:'BULLISH',color:C.green,alloc:45,reason:'GSE resilient'},
                    {label:'USD/Forex',signal:'HOLD',color:C.blue,alloc:25,reason:'GHS stable'},
                    {label:'Gold',signal:'BULLISH',color:C.gold,alloc:10,reason:'$3000+ momentum'},
                  ].map((s,i)=>(
                    <div key={i} style={{padding:'10px 0',borderBottom:`1px solid ${C.border}`}}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:6}}>
                        <span style={{fontSize:14,fontWeight:600}}>{s.label}</span>
                        <span style={{fontSize:12,color:s.color,fontWeight:700}}>{s.signal}</span>
                      </div>
                      <div style={{background:C.bg3,borderRadius:3,height:4,marginBottom:4}}>
                        <div style={{width:`${s.alloc}%`,height:4,background:s.color,borderRadius:3}}></div>
                      </div>
                      <div style={{fontSize:11,color:C.text3}}>{s.alloc}% allocation - {s.reason}</div>
                    </div>
                  ))}
                  <button onClick={()=>setPage('ai')} style={{width:'100%',marginTop:12,padding:'9px',background:`${C.gold}18`,border:`1px solid ${C.gold}`,borderRadius:5,color:C.gold,fontWeight:600,fontSize:13,cursor:'pointer'}}>
                    Ask ACCRA AI
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• MARKETS â•â•â• */}
          {page==='markets'&&(
            <div style={{display:'grid',gridTemplateColumns:'300px 1fr',gap:16}}>
              <div>
                <div style={cardStyle}>
                  <div style={headerStyle}>Exchanges</div>
                  {Object.entries(EXCHANGES).map(([k,ex])=>(
                    <div key={k} onClick={()=>setActiveEx(k)}
                      style={{padding:'10px 12px',borderRadius:5,cursor:'pointer',marginBottom:4,
                        background:activeEx===k?`${ex.color}18`:C.bg3,
                        border:`1px solid ${activeEx===k?ex.color:C.border}`}}
                      onMouseEnter={e=>e.currentTarget.style.borderColor=ex.color}
                      onMouseLeave={e=>e.currentTarget.style.borderColor=activeEx===k?ex.color:C.border}>
                      <div style={{fontSize:13,fontWeight:600,color:activeEx===k?ex.color:C.text}}>{k} - {ex.country}</div>
                      <div style={{fontSize:11,color:C.text3}}>{ex.name}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div style={cardStyle}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16}}>
                    <div style={headerStyle}>{activeEx} - {EXCHANGES[activeEx]?.name}</div>
                    <input value={searchQ} onChange={e=>setSearchQ(e.target.value)}
                      placeholder="Search stocks..." style={{background:C.bg3,border:`1px solid ${C.border}`,color:C.text,padding:'6px 12px',borderRadius:5,fontSize:13,width:200,outline:'none'}}/>
                  </div>

                  {selStock&&(
                    <div style={{marginBottom:16,padding:16,background:C.bg3,borderRadius:6,border:`1px solid ${C.border}`}}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:12}}>
                        <div>
                          <div style={{fontSize:18,fontWeight:700,color:C.gold}}>{selStock.t}</div>
                          <div style={{fontSize:13,color:C.text2}}>{selStock.n} - {selStock.s}</div>
                        </div>
                        <div style={{textAlign:'right'}}>
                          <div style={{...numStyle}}>{(selStock.p||0).toFixed(2)} {EXCHANGES[activeEx]?.currency}</div>
                          <div style={{fontSize:14,color:pc((selStock.p-selStock.pc)/selStock.pc*100),fontWeight:600}}>{fP((selStock.p-selStock.pc)/selStock.pc*100)}</div>
                        </div>
                      </div>
                      <TradingChart data={generateOHLC(selStock.p||1,40)} />
                      <button onClick={()=>sendChat(`Give me a detailed analysis of ${selStock.t} - ${selStock.n} stock. Include supply chain risks, political exposure, and trading recommendation.`)}
                        style={{marginTop:10,padding:'8px 16px',background:`${C.gold}20`,border:`1px solid ${C.gold}`,borderRadius:5,color:C.gold,fontWeight:600,cursor:'pointer',fontSize:13}}>
                        Analyze with AI
                      </button>
                    </div>
                  )}

                  <table style={{width:'100%',borderCollapse:'collapse'}}>
                    <thead>
                      <tr style={{borderBottom:`1px solid ${C.border}`}}>
                        {[['t','Ticker'],['p','Price'],['chg','Change'],['mc','Mkt Cap'],['v','Volume']].map(([k,h])=>(
                          <th key={k} onClick={()=>{setSortK(k);setSortD(d=>sortK===k?-d:-1);}}
                            style={{padding:'10px 8px',textAlign:'left',fontSize:12,color:sortK===k?C.gold:C.text3,fontWeight:600,cursor:'pointer',letterSpacing:0.5,userSelect:'none'}}>
                            {h}{sortK===k?(sortD>0?' v':' ^'):''}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {activeStocks.map((s,i)=>{
                        const chg=(s.p-s.pc)/s.pc*100;
                        return(
                          <tr key={i} onClick={()=>setSelStock(s)}
                            style={{borderBottom:`1px solid ${C.border}`,cursor:'pointer',transition:'background 0.1s'}}
                            onMouseEnter={e=>e.currentTarget.style.background=C.bg3}
                            onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                            <td style={{padding:'12px 8px',fontWeight:600,color:C.gold,fontSize:13}}>{s.t}</td>
                            <td style={{padding:'12px 8px',fontWeight:700,fontSize:14}}>{(s.p||0).toFixed(2)}</td>
                            <td style={{padding:'12px 8px',color:pc(chg),fontWeight:600,fontSize:13}}>{fP(chg)}</td>
                            <td style={{padding:'12px 8px',color:C.text2,fontSize:13}}>{fV(s.mc)}</td>
                            <td style={{padding:'12px 8px',color:C.text2,fontSize:13}}>{fV(s.v)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• CRYPTO â•â•â• */}
          {page==='crypto'&&(
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
              {[
                {id:'bitcoin',label:'Bitcoin',sym:'BTC',color:'#f7931a'},
                {id:'ethereum',label:'Ethereum',sym:'ETH',color:'#627eea'},
                {id:'solana',label:'Solana',sym:'SOL',color:'#9945ff'},
                {id:'binancecoin',label:'BNB',sym:'BNB',color:'#f3ba2f'},
              ].map(coin=>{
                const d=crypto[coin.id]||{};
                return(
                  <div key={coin.id} style={cardStyle}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
                      <div>
                        <div style={{fontSize:16,fontWeight:700,color:coin.color}}>{coin.sym}</div>
                        <div style={{fontSize:12,color:C.text3}}>{coin.label}</div>
                      </div>
                      <div style={{textAlign:'right'}}>
                        <div style={{...numStyle}}>${(d.usd||0).toLocaleString()}</div>
                        <div style={{fontSize:14,color:pc(d.usd_24h_change||0),fontWeight:600}}>{fP(d.usd_24h_change||0)}</div>
                      </div>
                    </div>
                    <TradingChart data={generateOHLC(d.usd||1000,30)} color={coin.color}/>
                    <button onClick={()=>sendChat(`Analyze ${coin.label} current price action and give a trading recommendation for a Ghanaian investor.`)}
                      style={{marginTop:10,width:'100%',padding:'8px',background:`${coin.color}15`,border:`1px solid ${coin.color}40`,borderRadius:5,color:coin.color,fontWeight:600,cursor:'pointer',fontSize:13}}>
                      AI Analysis
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* â•â•â• FOREX â•â•â• */}
          {page==='forex'&&(
            <div>
              <div style={{...cardStyle,marginBottom:16}}>
                <div style={headerStyle}>African Forex Monitor - USD Base</div>
                <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12}}>
                  {[
                    {k:'GHS',label:'Ghanaian Cedi',flag:'GH',threshold:15},
                    {k:'NGN',label:'Nigerian Naira',flag:'NG',threshold:1500},
                    {k:'ZAR',label:'South African Rand',flag:'ZA',threshold:18},
                    {k:'KES',label:'Kenyan Shilling',flag:'KE',threshold:130},
                    {k:'EGP',label:'Egyptian Pound',flag:'EG',threshold:48},
                    {k:'XOF',label:'West African CFA',flag:'WA',threshold:620},
                    {k:'EUR',label:'Euro',flag:'EU',threshold:null},
                    {k:'GBP',label:'British Pound',flag:'GB',threshold:null},
                  ].map(({k,label,flag,threshold})=>(
                    <div key={k} style={{...cardStyle,padding:14}}>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:6}}>
                        <div>
                          <div style={{fontSize:13,fontWeight:700,color:C.text}}>{flag} USD/{k}</div>
                          <div style={{fontSize:11,color:C.text3}}>{label}</div>
                        </div>
                        <div style={{textAlign:'right'}}>
                          <div style={{fontSize:18,fontWeight:700,color:threshold&&forex[k]>threshold?C.red:C.green}}>{(forex[k]||0).toFixed(2)}</div>
                          {threshold&&forex[k]>threshold&&<div style={{fontSize:10,color:C.red}}>Above threshold</div>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• PORTFOLIO â•â•â• */}
          {page==='portfolio'&&(
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
              <div style={cardStyle}>
                <div style={headerStyle}>Portfolio - P&L Tracker</div>
                <div style={{...numStyle,color:C.green,marginBottom:4}}>${portfolioValue.toFixed(2)}</div>
                <div style={{fontSize:14,color:C.green,marginBottom:20}}>+ 3.42% Today</div>
                <table style={{width:'100%',borderCollapse:'collapse'}}>
                  <thead>
                    <tr style={{borderBottom:`1px solid ${C.border}`}}>
                      {['Asset','Qty','Avg','Current','P&L'].map(h=>(
                        <th key={h} style={{padding:'8px 6px',textAlign:'left',fontSize:11,color:C.text3,fontWeight:600}}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.map((h,i)=>{
                      const price=h.sym==='BTC'?crypto.bitcoin?.usd:h.sym==='SOL'?crypto.solana?.usd:h.avg;
                      const pnl=((price||h.avg)-h.avg)*h.qty;
                      const pnlPct=((price||h.avg)-h.avg)/h.avg*100;
                      return(
                        <tr key={i} style={{borderBottom:`1px solid ${C.border}`}}>
                          <td style={{padding:'12px 6px',fontWeight:700,color:h.color}}>{h.sym}</td>
                          <td style={{padding:'12px 6px',color:C.text2}}>{h.qty}</td>
                          <td style={{padding:'12px 6px',color:C.text2}}>{h.avg.toFixed(2)}</td>
                          <td style={{padding:'12px 6px',fontWeight:700}}>{(price||h.avg).toFixed(2)}</td>
                          <td style={{padding:'12px 6px',color:pc(pnl),fontWeight:700}}>{pnl>0?'+':''}{pnl.toFixed(2)} ({fP(pnlPct)})</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div style={cardStyle}>
                <div style={headerStyle}>Allocation</div>
                {portfolio.map((h,i)=>{
                  const price=h.sym==='BTC'?crypto.bitcoin?.usd:h.sym==='SOL'?crypto.solana?.usd:h.avg;
                  const val=(price||h.avg)*h.qty;
                  const pct=portfolioValue>0?val/portfolioValue*100:0;
                  return(
                    <div key={i} style={{marginBottom:12}}>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:4}}>
                        <span style={{fontSize:13,fontWeight:600,color:h.color}}>{h.sym}</span>
                        <span style={{fontSize:13,fontWeight:700}}>{pct.toFixed(1)}%</span>
                      </div>
                      <div style={{background:C.bg3,borderRadius:3,height:6}}>
                        <div style={{width:`${pct}%`,height:6,background:h.color,borderRadius:3}}></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* â•â•â• RISK RADAR â•â•â• */}
          {page==='risk'&&(
            <div style={cardStyle}>
              <div style={headerStyle}>Risk Radar - Pan-African Intelligence</div>
              {RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)).map(e=>(
                <div key={e.id} style={{padding:16,marginBottom:12,background:C.bg3,borderRadius:6,border:`1px solid ${sevC(e.severity)}40`,borderLeft:`4px solid ${sevC(e.severity)}`}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:8}}>
                    <div>
                      <div style={{fontSize:15,fontWeight:600,color:C.text,marginBottom:4}}>{e.title}</div>
                      <div style={{display:'flex',gap:12,fontSize:12,color:C.text3}}>
                        <span>{e.region}</span>
                        <span>{e.source}</span>
                        <span>{e.time}</span>
                      </div>
                    </div>
                    <div style={{display:'flex',gap:8,alignItems:'center'}}>
                      <span style={{fontSize:12,color:sevC(e.severity),background:`${sevC(e.severity)}18`,padding:'3px 10px',borderRadius:4,fontWeight:700}}>{e.severity}</span>
                      <button onClick={()=>setDismissedRisks(prev=>new Set([...prev,e.id]))} style={{background:'transparent',border:`1px solid ${C.border}`,color:C.text3,padding:'3px 8px',borderRadius:4,cursor:'pointer',fontSize:12}}>Dismiss</button>
                    </div>
                  </div>
                  <div style={{fontSize:13,color:C.text2,marginBottom:10}}>{e.desc}</div>
                  <button onClick={()=>{sendChat(`Analyze this risk event for African markets: ${e.title} - ${e.desc}`);setPage('ai');}}
                    style={{padding:'6px 14px',background:`${C.gold}18`,border:`1px solid ${C.gold}`,borderRadius:4,color:C.gold,fontWeight:600,cursor:'pointer',fontSize:12}}>
                    Analyze Impact
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* â•â•â• SUPPLY CHAIN â•â•â• */}
          {page==='supply'&&(
            <div style={cardStyle}>
              <div style={headerStyle}>Supply Chain Intelligence - GSE Stocks</div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(300px,1fr))',gap:16}}>
                {Object.entries(SUPPLY_CHAIN).map(([ticker,sc])=>(
                  <div key={ticker} style={{background:C.bg3,borderRadius:6,padding:14,border:`1px solid ${C.border}`}}>
                    <div style={{fontSize:15,fontWeight:700,color:C.gold,marginBottom:4}}>{ticker}</div>
                    <div style={{fontSize:12,color:C.text3,marginBottom:10}}>Parent: {sc.parent}</div>
                    {sc.risks.map((r,i)=>{
                      const sev=r.includes('CRITICAL')?C.red:r.includes('HIGH')?C.orange:C.yellow;
                      return<div key={i} style={{fontSize:12,color:sev,padding:'3px 0',borderBottom:`1px solid ${C.border}`}}>{r}</div>;
                    })}
                    <button onClick={()=>{sendChat(`Analyze supply chain risks for ${ticker} - ${sc.parent}. Include geopolitical risks and ECG dependency.`);setPage('ai');}}
                      style={{marginTop:10,padding:'6px 12px',background:`${C.gold}15`,border:`1px solid ${C.gold}`,borderRadius:4,color:C.gold,fontSize:12,fontWeight:600,cursor:'pointer'}}>
                      Deep Analysis
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* â•â•â• POLITICS â•â•â• */}
          {page==='map'&&(
            <div>
              <div style={{...cardStyle,marginBottom:16}}>
                <div style={headerStyle}>Political Risk - 6 African Markets</div>
                <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',gap:14}}>
                  {Object.entries(POLITICAL_RISK).map(([k,pol])=>(
                    <div key={k} style={{background:C.bg3,borderRadius:6,padding:14,border:`1px solid ${sevC(pol.riskLevel)}40`,borderTop:`3px solid ${sevC(pol.riskLevel)}`}}>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
                        <div style={{fontSize:15,fontWeight:700,color:C.text}}>{pol.country}</div>
                        <span style={{fontSize:11,color:sevC(pol.riskLevel),background:`${sevC(pol.riskLevel)}18`,padding:'2px 8px',borderRadius:3,fontWeight:700}}>{pol.riskLevel}</span>
                      </div>
                      <div style={{fontSize:13,color:C.text2,marginBottom:4}}>{pol.leader} - {pol.party}</div>
                      <div style={{marginBottom:6}}>
                        <div style={{fontSize:11,color:C.text3,marginBottom:3}}>Approval: {pol.approvalPct}%</div>
                        <div style={{background:C.border,borderRadius:3,height:4}}>
                          <div style={{width:`${pol.approvalPct}%`,height:4,background:pol.approvalPct>50?C.green:pol.approvalPct>35?C.yellow:C.red,borderRadius:3}}></div>
                        </div>
                      </div>
                      <div style={{fontSize:12,color:C.text3}}>{pol.notes}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• BOT SIGNALS â•â•â• */}
          {page==='bot'&&(
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
              <div style={cardStyle}>
                <div style={headerStyle}>AI Bot Control Panel</div>
                <select value={botCoin} onChange={e=>setBotCoin(e.target.value)} style={{width:'100%',background:C.bg3,border:`1px solid ${C.border}`,color:C.text,padding:'10px 12px',borderRadius:5,marginBottom:12,fontSize:14,outline:'none'}}>
                  {[['bitcoin','Bitcoin (BTC)'],['ethereum','Ethereum (ETH)'],['solana','Solana (SOL)'],['binancecoin','BNB']].map(([v,l])=>(
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
                <button onClick={()=>setBotRunning(r=>!r)} style={{width:'100%',padding:'12px',background:botRunning?`${C.red}20`:C.green,border:`1px solid ${botRunning?C.red:C.green}`,borderRadius:6,color:botRunning?C.red:'#000',fontWeight:700,fontSize:16,cursor:'pointer',marginBottom:16}}>
                  {botRunning?'Stop Bot':'Start Bot'}
                </button>
                {botSig&&(
                  <div>
                    <div style={{textAlign:'center',padding:20,background:C.bg3,borderRadius:6,marginBottom:12}}>
                      <div style={{fontSize:36,fontWeight:700,color:botSig.signal==='BUY'?C.green:botSig.signal==='SELL'?C.red:C.yellow,letterSpacing:3}}>{botSig.signal}</div>
                      <div style={{fontSize:20,fontWeight:600,color:C.text2,marginTop:6}}>{botSig.confidence}% confidence</div>
                      <div style={{fontSize:14,color:C.text3,marginTop:4}}>{botCoin.toUpperCase()} @ ${(botSig.price||0).toFixed(4)}</div>
                    </div>
                    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
                      {[['RSI',botSig.rsi],['MACD',botSig.macd],['Stop Loss',`$${botSig.sl}`],['Take Profit',`$${botSig.tp}`]].map(([k,v])=>(
                        <div key={k} style={{background:C.bg3,borderRadius:5,padding:'10px 12px',border:`1px solid ${C.border}`}}>
                          <div style={{fontSize:11,color:C.text3,marginBottom:3}}>{k}</div>
                          <div style={{fontSize:16,fontWeight:700,color:C.text}}>{v}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div style={cardStyle}>
                <div style={headerStyle}>Signal Log</div>
                <div style={{overflowY:'auto',maxHeight:500}}>
                  {botLog.length===0?<div style={{color:C.text3,fontSize:13,textAlign:'center',padding:20}}>No signals yet. Start the bot.</div>:botLog.map((log,i)=>(
                    <div key={i} style={{padding:'10px 0',borderBottom:`1px solid ${C.border}`}}>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:4}}>
                        <span style={{fontSize:13,fontWeight:700,color:log.action==='BUY'?C.green:log.action==='SELL'?C.red:C.yellow}}>{log.action}</span>
                        <span style={{fontSize:11,color:C.text3}}>{log.time}</span>
                      </div>
                      <div style={{fontSize:12,color:C.text2}}>{log.coin} @ ${(log.price||0).toFixed(4)} | RSI:{log.rsi} | Conf:{log.confidence}%</div>
                      <div style={{fontSize:11,color:C.text3}}>{log.reasons}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• FREEDOM TRACKER â•â•â• */}
          {page==='freedom'&&(
            <div style={cardStyle}>
              <div style={headerStyle}>Freedom Tracker - Financial Independence</div>
              <div style={{fontSize:32,fontWeight:700,color:C.gold,marginBottom:4}}>
                GHS {Object.values(freedom).reduce((s,v)=>s+v,0).toLocaleString()}
              </div>
              <div style={{fontSize:14,color:C.text3,marginBottom:24}}>Total progress toward financial freedom</div>
              {[
                {id:'terminal',label:'Accra Terminal',target:2500,plan:'500 users x $5/mo',color:C.green},
                {id:'crypto',label:'Crypto Portfolio',target:500,plan:'DCA BTC/SOL',color:C.blue},
                {id:'gse',label:'GSE Dividends',target:300,plan:'MTNGH + GCB',color:C.gold},
                {id:'hydro',label:'HydroLife Revenue',target:200,plan:'Product sales',color:C.orange},
                {id:'btcstack',label:'BTC Stack',target:200,plan:'Monthly DCA',color:'#f7931a'},
              ].map(goal=>{
                const current=freedom[goal.id]||0;
                const pct=Math.min(100,current/goal.target*100);
                return(
                  <div key={goal.id} style={{marginBottom:20,padding:16,background:C.bg3,borderRadius:6,border:`1px solid ${C.border}`}}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>
                      <div>
                        <div style={{fontSize:15,fontWeight:600,color:goal.color}}>{goal.label}</div>
                        <div style={{fontSize:12,color:C.text3}}>{goal.plan}</div>
                      </div>
                      <div style={{textAlign:'right'}}>
                        <div style={{fontSize:16,fontWeight:700}}>${current} / ${goal.target}</div>
                        <div style={{fontSize:12,color:goal.color}}>{pct.toFixed(0)}% complete</div>
                      </div>
                    </div>
                    <div style={{background:C.border,borderRadius:4,height:8}}>
                      <div style={{width:`${pct}%`,height:8,background:goal.color,borderRadius:4,transition:'width 0.5s'}}></div>
                    </div>
                    <input type="number" placeholder="Update amount ($)" min="0"
                      onBlur={e=>{if(e.target.value) setFreedom(prev=>({...prev,[goal.id]:+e.target.value}));}}
                      style={{marginTop:10,width:'100%',background:C.bg,border:`1px solid ${C.border}`,color:C.text,padding:'6px 10px',borderRadius:5,fontSize:13,outline:'none',boxSizing:'border-box'}}/>
                  </div>
                );
              })}
            </div>
          )}

          {/* â•â•â• NEWS â•â•â• */}
          {page==='news'&&(
            <div style={cardStyle}>
              <div style={headerStyle}>Market Intelligence Feed</div>
              {[
                {title:'Ghana IMF quarterly review on track - BoG signals cedi stabilisation by Q3',tag:'IMF',color:C.blue,time:'2h ago',source:'Bloomberg Africa',impact:'HIGH'},
                {title:'ECG load shedding extended to 12 hours - FML, MTNGH, GGBL operations disrupted',tag:'ECG',color:C.red,time:'4h ago',source:'Joy Business',impact:'HIGH'},
                {title:'Bitcoin Fear & Greed index hits 16 - extreme fear territory, historical buy signal',tag:'Crypto',color:C.yellow,time:'30m ago',source:'CoinGecko',impact:'MEDIUM'},
                {title:'Dangote Cement Q1 2026 results beat expectations by 18% - NGX rallying',tag:'Earnings',color:C.green,time:'1d ago',source:'NGX Group',impact:'HIGH'},
                {title:'Gold surges above $3,000/oz - NEWGOLD ETF outperforms GSE peers',tag:'Gold',color:C.gold,time:'6h ago',source:'Reuters',impact:'MEDIUM'},
                {title:'MTN Ghana reports 22% revenue growth despite load shedding headwinds',tag:'Earnings',color:C.green,time:'2d ago',source:'GSE',impact:'HIGH'},
                {title:'World Bank approves $500M Ghana infrastructure grant',tag:'Macro',color:C.blue,time:'3d ago',source:'World Bank',impact:'MEDIUM'},
                {title:'Naira strengthens to N1,480 after CBN intervention',tag:'Forex',color:C.green,time:'1d ago',source:'CBN',impact:'MEDIUM'},
              ].map((n,i)=>(
                <div key={i} style={{padding:16,borderBottom:`1px solid ${C.border}`,cursor:'pointer',transition:'background 0.1s'}}
                  onMouseEnter={e=>e.currentTarget.style.background=C.bg3}
                  onMouseLeave={e=>e.currentTarget.style.background='transparent'}
                  onClick={()=>{sendChat(`Analyze this news for African investors: ${n.title}`);setPage('ai');}}>
                  <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:6}}>
                    <span style={{fontSize:11,color:n.color,background:`${n.color}18`,padding:'2px 8px',borderRadius:3,fontWeight:700}}>{n.tag}</span>
                    <span style={{fontSize:11,color:sevC(n.impact),background:`${sevC(n.impact)}15`,padding:'2px 8px',borderRadius:3,fontWeight:600}}>{n.impact} IMPACT</span>
                    <span style={{fontSize:11,color:C.text3,marginLeft:'auto'}}>{n.source} - {n.time}</span>
                  </div>
                  <div style={{fontSize:14,color:C.text,lineHeight:1.6,fontWeight:500}}>{n.title}</div>
                </div>
              ))}
            </div>
          )}

          {/* â•â•â• AI ASSISTANT â•â•â• */}
          {page==='ai'&&(
            <div style={{display:'grid',gridTemplateColumns:'1fr 280px',gap:16,height:'calc(100vh - 140px)'}}>
              <div style={{...cardStyle,display:'flex',flexDirection:'column',padding:0,overflow:'hidden'}}>
                {/* AI Header */}
                <div style={{padding:'14px 20px',borderBottom:`1px solid ${C.border}`,display:'flex',gap:8,alignItems:'center'}}>
                  <div style={{width:32,height:32,borderRadius:'50%',background:`${C.gold}20`,border:`1px solid ${C.gold}`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,fontWeight:700,color:C.gold}}>AI</div>
                  <div>
                    <div style={{fontSize:14,fontWeight:600,color:C.gold}}>ACCRA AI Assistant</div>
                    <div style={{fontSize:11,color:C.text3}}>Africa-focused financial intelligence</div>
                  </div>
                </div>

                {/* Messages */}
                <div style={{flex:1,overflowY:'auto',padding:20}}>
                  {msgs.map((m,i)=>(
                    <div key={i} style={{marginBottom:16,display:'flex',flexDirection:'column',alignItems:m.role==='user'?'flex-end':'flex-start'}}>
                      {m.role==='assistant'&&<div style={{fontSize:10,color:m.color||C.gold,marginBottom:4,fontWeight:600}}>{m.label||'ACCRA AI'}</div>}
                      <div style={{maxWidth:'85%',padding:'12px 16px',borderRadius:m.role==='user'?'12px 12px 0 12px':'12px 12px 12px 0',
                        background:m.role==='user'?`${C.accent}80`:C.bg3,
                        border:`1px solid ${m.role==='user'?C.accent:C.border}`,
                        fontSize:14,lineHeight:1.7,color:C.text,whiteSpace:'pre-wrap'}}>
                        {m.content}
                      </div>
                    </div>
                  ))}
                  {chatLoading&&<div style={{padding:'12px 16px',background:C.bg3,borderRadius:8,border:`1px solid ${C.border}`,maxWidth:'60%',color:C.text3,fontSize:13}}>ACCRA is analyzing...</div>}
                  <div ref={chatEndRef}/>
                </div>

                {/* Input */}
                <div style={{padding:'12px 20px',borderTop:`1px solid ${C.border}`,display:'flex',gap:10}}>
                  <input value={chatInput} onChange={e=>setChatInput(e.target.value)}
                    onKeyDown={e=>e.key==='Enter'&&!e.shiftKey&&sendChat()}
                    placeholder="Ask about any African market, stock, or trading signal..."
                    style={{flex:1,background:C.bg3,border:`1px solid ${C.border}`,color:C.text,padding:'10px 14px',borderRadius:6,fontSize:14,outline:'none',fontFamily:'inherit'}}/>
                  <button onClick={()=>sendChat()} disabled={chatLoading}
                    style={{padding:'10px 20px',background:chatLoading?C.bg3:C.gold,border:'none',borderRadius:6,color:'#000',fontWeight:700,fontSize:14,cursor:chatLoading?'default':'pointer'}}>
                    Send
                  </button>
                </div>
              </div>

              {/* Quick Actions */}
              <div style={{display:'flex',flexDirection:'column',gap:10}}>
                <div style={cardStyle}>
                  <div style={{fontSize:14,fontWeight:600,marginBottom:12,color:C.text}}>Quick Analysis</div>
                  {[
                    'Analyze MTNGH vs ECG load shedding risk',
                    'What is the best GSE stock to buy now?',
                    'Explain Ghana IMF program impact on GHS',
                    'Bitcoin outlook for African investors',
                    'Compare NGX vs GSE performance',
                    'Supply chain risks for FML stock',
                  ].map((q,i)=>(
                    <div key={i} onClick={()=>sendChat(q)}
                      style={{padding:'8px 10px',marginBottom:6,background:C.bg3,borderRadius:5,cursor:'pointer',fontSize:12,color:C.text2,border:`1px solid ${C.border}`,lineHeight:1.4,transition:'all 0.1s'}}
                      onMouseEnter={e=>{e.currentTarget.style.borderColor=C.gold;e.currentTarget.style.color=C.gold;}}
                      onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.color=C.text2;}}>
                      {q}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* â•â•â• ALERTS â•â•â• */}
          {page==='alerts'&&(
            <div style={cardStyle}>
              <div style={headerStyle}>All Alerts - {RISK_EVENTS.filter(e=>!dismissedRisks.has(e.id)).length} Active</div>
              {RISK_EVENTS.map(a=>(
                !dismissedRisks.has(a.id)&&(
                  <div key={a.id} style={{padding:16,marginBottom:10,background:C.bg3,borderRadius:6,border:`1px solid ${sevC(a.severity)}40`,borderLeft:`4px solid ${sevC(a.severity)}`}}>
                    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                      <div style={{fontSize:15,fontWeight:600,color:C.text}}>{a.title}</div>
                      <button onClick={()=>setDismissedRisks(prev=>new Set([...prev,a.id]))}
                        style={{background:'transparent',border:`1px solid ${C.border}`,color:C.text3,padding:'3px 10px',borderRadius:4,cursor:'pointer',fontSize:12}}>x</button>
                    </div>
                    <div style={{fontSize:12,color:C.text3,margin:'6px 0'}}>{a.region} - {a.source} - {a.time}</div>
                    <div style={{fontSize:13,color:C.text2}}>{a.desc}</div>
                  </div>
                )
              ))}
            </div>
          )}

          {/* â•â•â• SETTINGS â•â•â• */}

          {page==='botlive'&&(
            <div>
              {!realBal&&(<button onClick={fetchRealBal} style={{width:'100%',padding:12,marginBottom:16,background:'#f0b90b18',border:'1px solid #f0b90b',borderRadius:8,color:'#f0b90b',fontWeight:700,fontSize:14,cursor:'pointer'}}>{realBalLoading?'Loading...':'Load Real Portfolio'}</button>)}
              {realBal&&(<div style={{marginBottom:16,padding:16,borderRadius:8,border:'1px solid #f0b90b44',background:'#f0b90b08'}}><div style={{display:'flex',justifyContent:'space-between',marginBottom:12}}><span style={{fontWeight:700,color:'#f0b90b'}}>REAL PORTFOLIO</span><span style={{fontSize:11,opacity:0.5}}>{realBal.updated}</span></div><div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8}}>{[['USDT','$'+realBal.usdt,'#e0e0e0'],['SOL','$'+realBal.sol_value,'#00d4aa'],['Total','$'+realBal.total,'#f0b90b'],['PnL',realBal.pnl_pct+'%',parseFloat(realBal.pnl_pct)>=0?'#00d4aa':'#ff4444']].map(([l,v,c])=>(<div key={l} style={{textAlign:'center',padding:'8px 4px',background:'#ffffff08',borderRadius:6}}><div style={{fontSize:10,opacity:0.6,marginBottom:2}}>{l}</div><div style={{fontSize:14,fontWeight:700,color:c}}>{v}</div></div>))}</div></div>)}
              {/* Market Status */}
              <div style={{marginBottom:12,padding:10,borderRadius:6,background:'#00d4aa11',border:'1px solid #00d4aa44',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <span style={{fontSize:11,color:'#00d4aa',fontWeight:700}}>● MARKET FILTER ACTIVE</span>
                <span style={{fontSize:10,opacity:0.5}}>Bot trades only in favourable conditions</span>
              </div>
              {/* Bot Connection Status */}
              <div style={{display:'flex',gap:12,marginBottom:16,alignItems:'center'}}>
                <div style={{...cardStyle,flex:1,padding:'12px 16px'}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    <div>
                      <div style={{fontSize:16,fontWeight:600,color:C.text}}>ACCRA BOT v9 - MULTI-AI</div>
                      <div style={{fontSize:12,color:C.text3}}>Groq + Gemini + OpenRouter</div>
                    </div>
                    <div style={{display:'flex',alignItems:'center',gap:8}}>
                      <div style={{width:8,height:8,borderRadius:'50%',background:botConnected?C.green:C.red}}></div>
                      <span style={{fontSize:13,fontWeight:600,color:botConnected?C.green:C.red}}>{botConnected?'CONNECTED':'OFFLINE'}</span>
                    </div>
                  </div>
                </div>
                {botStatus&&(
                  <div style={{...cardStyle,flex:1,padding:'12px 16px'}}>
                    <div style={{fontSize:12,color:C.text3,marginBottom:4}}>Last Update</div>
                    <div style={{fontSize:13,fontWeight:600}}>{new Date(botStatus.timestamp).toLocaleTimeString()}</div>
                    <div style={{fontSize:11,color:C.text3}}>Cycle {botStatus.cycle} | {botStatus.assets_scanned} assets scanned</div>
                  </div>
                )}
              </div>

              {botStatus?(
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:16,marginBottom:16}}>
                  {/* Stats */}
                  <div style={cardStyle}>
                    <div style={{fontSize:14,fontWeight:600,marginBottom:12,color:C.text}}>Live Statistics</div>
                    {[
                      ['Mode',botStatus.strategy?.toUpperCase()],
                      ['Market',botStatus.market_condition],
                      ['Assets Scanned',botStatus.assets_scanned],
                      ['Open Trades',botStatus.open_trades],
                      ['BUY Signals',botStatus.buy_signals],
                      ['SELL Signals',botStatus.sell_signals],
                      ['Crypto',botStatus.markets?.crypto],
                      ['Stocks',botStatus.markets?.stocks],
                      ['HFM',botStatus.markets?.hfm],
                    ].map(([k,v])=>(
                      <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'6px 0',borderBottom:`1px solid ${C.border}`}}>
                        <span style={{fontSize:12,color:C.text3}}>{k}</span>
                        <span style={{fontSize:12,fontWeight:600,color:C.text}}>{String(v||'--')}</span>
                      </div>
                    ))}
                  </div>

                  {/* Open Positions */}
                  <div style={cardStyle}>
                    <div style={{fontSize:14,fontWeight:600,marginBottom:12,color:C.text}}>Open Positions</div>
                    {botStatus.open_positions?.length===0&&<div style={{fontSize:12,color:C.text3,textAlign:'center',padding:20}}>No open positions</div>}
                    {botStatus.open_positions?.map((p,i)=>(
                      <div key={i} style={{padding:'8px 0',borderBottom:`1px solid ${C.border}`}}>
                        <div style={{display:'flex',justifyContent:'space-between',marginBottom:3}}>
                          <span style={{fontSize:13,fontWeight:700,color:C.gold}}>{p.symbol}</span>
                          <span style={{fontSize:11,color:C.text3}}>{p.market?.toUpperCase()}</span>
                        </div>
                        <div style={{fontSize:11,color:C.text2}}>Entry: {p.entry?.toFixed(4)}</div>
                        <div style={{fontSize:11,color:C.red}}>SL: {p.sl?.toFixed(4)}</div>
                        <div style={{fontSize:11,color:C.green}}>TP: {p.tp?.toFixed(4)}</div>
                      </div>
                    ))}
                  </div>

                  {/* Strategy Control */}
                  <div style={cardStyle}>
                    <div style={{fontSize:14,fontWeight:600,marginBottom:12,color:C.text}}>Strategy Control</div>
                    <div style={{marginBottom:12}}>
                      <div style={{fontSize:12,color:C.text3,marginBottom:6}}>Trading Mode</div>
                      <div style={{display:'flex',gap:6}}>
                        {['conservative','balanced','aggressive'].map(m=>(
                          <div key={m} onClick={()=>pushStrategy({mode:m})}
                            style={{flex:1,padding:'6px 4px',textAlign:'center',borderRadius:5,cursor:'pointer',fontSize:11,fontWeight:600,
                              background:botStrategy.mode===m?`${C.gold}30`:C.bg3,
                              border:`1px solid ${botStrategy.mode===m?C.gold:C.border}`,
                              color:botStrategy.mode===m?C.gold:C.text3}}>
                            {m.charAt(0).toUpperCase()+m.slice(1)}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div style={{marginBottom:12}}>
                      <div style={{fontSize:12,color:C.text3,marginBottom:6}}>Market Condition</div>
                      <div style={{display:'flex',gap:6}}>
                        {['bear','neutral','bull'].map(m=>(
                          <div key={m} onClick={()=>pushStrategy({market_condition:m})}
                            style={{flex:1,padding:'6px 4px',textAlign:'center',borderRadius:5,cursor:'pointer',fontSize:11,fontWeight:600,
                              background:botStrategy.market_condition===m?(m==='bull'?`${C.green}30`:m==='bear'?`${C.red}30`:`${C.yellow}30`):C.bg3,
                              border:`1px solid ${botStrategy.market_condition===m?(m==='bull'?C.green:m==='bear'?C.red:C.yellow):C.border}`,
                              color:botStrategy.market_condition===m?(m==='bull'?C.green:m==='bear'?C.red:C.yellow):C.text3}}>
                            {m.charAt(0).toUpperCase()+m.slice(1)}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div style={{marginBottom:12}}>
                      <div style={{fontSize:12,color:C.text3,marginBottom:6}}>Min Confidence: {botStrategy.min_confidence}%</div>
                      <input type="range" min="25" max="70" value={botStrategy.min_confidence}
                        onChange={e=>setBotStrategy(prev=>({...prev,min_confidence:+e.target.value}))}
                        style={{width:'100%'}}/>
                    </div>
                    <div style={{marginBottom:12}}>
                      <div style={{fontSize:12,color:C.text3,marginBottom:6}}>Enable Markets</div>
                      {[['crypto','Crypto'],['stocks','Stocks'],['hfm','HFM/Forex']].map(([k,label])=>(
                        <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'4px 0'}}>
                          <span style={{fontSize:12,color:C.text2}}>{label}</span>
                          <div onClick={async()=>{const newVal=!botStrategy[k+'_enabled'];setBotStrategy(prev=>({...prev,[k+'_enabled']:newVal}));try{const s={...botStrategy,[k+'_enabled']:newVal,updated_by:'terminal',last_updated:new Date().toISOString()};await fetch('https://api.github.com/gists/4f5f6918288ddaec0a1fc998af3e6f99',{method:'PATCH',headers:{'Authorization':'Bearer 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','Content-Type':'application/json'},body:JSON.stringify({files:{'bot_strategy.json':{content:JSON.stringify(s,null,2)}}})});}catch(e){console.error(e);}}}
                            style={{width:36,height:20,borderRadius:10,cursor:'pointer',position:'relative',
                              background:botStrategy[k+'_enabled']?C.green:C.border}}>
                            <div style={{position:'absolute',top:2,left:botStrategy[k+'_enabled']?18:2,
                              width:16,height:16,borderRadius:'50%',background:'#fff',transition:'left 0.2s'}}></div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <button onClick={async()=>{
                        setAiLoading(true);setAiRec('');
                        const fg=fearGreed?.value||50;
                        const btc=crypto.bitcoin?.usd||0;
                        const top=botStatus?.top_opportunities?.[0];
                        const prompt=`Trading strategy AI. Fear&Greed=${fg}/100, BTC=$${btc.toLocaleString()}, USD/GHS=${forex.GHS?.toFixed(2)||'N/A'}, Assets scanned=${botStatus?.assets_scanned||0}, Open trades=${botStatus?.open_trades||0}, Top signal=${top?.symbol||'none'} score=${top?.score||0}. Recommend strategy. Reply ONLY valid JSON no markdown: {"mode":"conservative|balanced|aggressive","market_condition":"bear|neutral|bull","min_confidence":35,"reason":"2 sentences","action":"what to do now"}`;
                        try{
                          const res=await fetch('https://api.groq.com/openai/v1/chat/completions',{method:'POST',headers:{'Authorization':'Bearer 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','Content-Type':'application/json'},body:JSON.stringify({model:'llama-3.3-70b-versatile',max_tokens:200,temperature:0.1,messages:[{role:'system',content:'Return valid JSON only.'},{role:'user',content:prompt}]})});
                          const d=await res.json();
                          const p=JSON.parse(d.choices[0].message.content.trim());
                          setBotStrategy(prev=>({...prev,mode:p.mode||prev.mode,market_condition:p.market_condition||prev.market_condition,min_confidence:p.min_confidence||35}));
                          setAiRec(p.reason+' '+p.action);
                        }catch(e){setAiRec('AI analysis failed. Try again.');}
                        setAiLoading(false);
                      }}
                      style={{width:'100%',padding:'9px',background:`${C.gold}18`,border:`1px solid ${C.gold}`,borderRadius:5,color:C.gold,fontWeight:600,fontSize:13,cursor:'pointer'}}>
                      {aiLoading?'Analyzing market...':'Ask AI for Strategy'}
                    </button>
                    {aiRec&&(<div style={{marginTop:8,padding:'8px 10px',background:C.bg3,borderRadius:5,fontSize:12,color:C.text2,lineHeight:1.6,border:`1px solid ${C.border}`}}><b style={{color:C.gold}}>AI Recommendation:</b><br/>{aiRec}</div>)}
{pendingStrategy&&(
  <div style={{marginTop:8}}>
    <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Pending: Mode={pendingStrategy.mode} | Market={pendingStrategy.market_condition} | Confidence={pendingStrategy.min_confidence}%</div>
    <div style={{display:'flex',gap:6}}>
      <button onClick={()=>approveStrategy(pendingStrategy)}
        style={{flex:1,padding:'8px',background:`${C.green}20`,border:`1px solid ${C.green}`,borderRadius:5,color:C.green,fontWeight:700,fontSize:12,cursor:'pointer'}}>
        {approving?'Sending to Bot...':'APPROVE - Send to Bot'}
      </button>
      <button onClick={()=>setPendingStrategy(null)}
        style={{padding:'8px 12px',background:`${C.red}20`,border:`1px solid ${C.red}`,borderRadius:5,color:C.red,fontWeight:600,fontSize:12,cursor:'pointer'}}>
        Reject
      </button>
    </div>
  </div>
)}
                  </div>
                </div>
              ):(
                <div style={{...cardStyle,textAlign:'center',padding:40}}>
                  <div style={{fontSize:16,color:C.text3,marginBottom:8}}>Bot not connected</div>
                  <div style={{fontSize:13,color:C.text3}}>Make sure bot.py is running on Termux</div>
                </div>
              )}

              {/* Top Opportunities */}
              {botStatus?.top_opportunities?.length>0&&(
                <div style={cardStyle}>
                  <div style={{fontSize:14,fontWeight:600,marginBottom:12,color:C.text}}>Top Opportunities This Cycle</div>
                  <table style={{width:'100%',borderCollapse:'collapse'}}>
                    <thead>
                      <tr style={{borderBottom:`1px solid ${C.border}`}}>
                        {['Symbol','Market','Signal','Score','Tech','Fund','Ghana Impact'].map(h=>(
                          <th key={h} style={{padding:'8px 6px',textAlign:'left',fontSize:11,color:C.text3,fontWeight:600}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {botStatus.top_opportunities.map((o,i)=>(
                        <tr key={i} style={{borderBottom:`1px solid ${C.border}`,cursor:'pointer'}}
                          onMouseEnter={e=>e.currentTarget.style.background=C.bg3}
                          onMouseLeave={e=>e.currentTarget.style.background='transparent'}
                          onClick={()=>sendChat(`Analyze ${o.symbol} - score:${o.score}, market:${o.market}. ${o.reason}`)}>
                          <td style={{padding:'10px 6px',fontWeight:700,color:C.gold,fontSize:13}}>{o.symbol}</td>
                          <td style={{padding:'10px 6px',fontSize:12,color:C.text3}}>{o.market?.toUpperCase()}</td>
                          <td style={{padding:'10px 6px',fontSize:13,fontWeight:600,color:o.signal==='BUY'?C.green:o.signal==='SELL'?C.red:C.yellow}}>{o.signal}</td>
                          <td style={{padding:'10px 6px',fontSize:13,fontWeight:700,color:o.score>0?C.green:o.score<0?C.red:C.yellow}}>{o.score>0?'+':''}{o.score}</td>
                          <td style={{padding:'10px 6px',fontSize:12,color:C.text2}}>{o.tech>0?'+':''}{o.tech}</td>
                          <td style={{padding:'10px 6px',fontSize:12,color:C.text2}}>{o.fund>0?'+':''}{o.fund}</td>
                          <td style={{padding:'10px 6px',fontSize:11,color:C.text3,maxWidth:200}}>{o.ghana?.slice(0,60)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {page==='settings'&&(
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
              <div style={cardStyle}>
                <div style={headerStyle}>API Configuration</div>
                {[
                  {label:'Anthropic API Key',placeholder:'sk-ant-...'},
                  {label:'Groq API Key',placeholder:'gsk_...'},
                  {label:'Valley Africa Key',placeholder:'live_...'},
                ].map(({label,placeholder})=>(
                  <div key={label} style={{marginBottom:16}}>
                    <div style={{fontSize:13,color:C.text2,marginBottom:6}}>{label}</div>
                    <input type="password" placeholder={placeholder}
                      style={{width:'100%',background:C.bg3,border:`1px solid ${C.border}`,color:C.text,padding:'10px 12px',borderRadius:5,fontSize:13,outline:'none',boxSizing:'border-box'}}/>
                  </div>
                ))}
              </div>
              <div style={cardStyle}>
                <div style={headerStyle}>About</div>
                <div style={{fontSize:14,color:C.text2,lineHeight:1.8}}>
                  <div style={{marginBottom:8}}><strong style={{color:C.gold}}>Accra Terminal V16</strong></div>
                  <div>Africa's #1 Financial Intelligence Platform</div>
                  <div style={{marginTop:8,color:C.text3}}>Built by HydroLife Studios</div>
                  <div style={{color:C.text3}}>Ashanti Region, Ghana</div>
                  <div style={{marginTop:16,padding:12,background:C.bg3,borderRadius:5,border:`1px solid ${C.border}`}}>
                    <div style={{fontSize:12,color:C.text3}}>Exchanges: GSE, NGX, JSE, NSE, EGX, BRVM</div>
                    <div style={{fontSize:12,color:C.text3}}>Data: Valley Africa, CoinGecko, Frankfurter</div>
                    <div style={{fontSize:12,color:C.text3}}>AI: Claude Sonnet 4 + Groq Llama 3.3</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TradingChart({data,color='#f5a623'}){
  const ref=useRef(null);
  useEffect(()=>{
    if(!ref.current||!data?.length) return;
    let chart;
    loadScript(LW_CDN).then(()=>{
      if(!window.LightweightCharts||!ref.current) return;
      ref.current.innerHTML='';
      chart=window.LightweightCharts.createChart(ref.current,{
        width:ref.current.offsetWidth,height:160,
        layout:{background:{color:'transparent'},textColor:'#5a6a7a'},
        grid:{vertLines:{color:'#1e2d47'},horzLines:{color:'#1e2d47'}},
        crosshair:{mode:1},
        rightPriceScale:{borderColor:'#1e2d47'},
        timeScale:{borderColor:'#1e2d47',timeVisible:false},
      });
      const series=chart.addCandlestickSeries({
        upColor:color,downColor:'#ff1744',borderUpColor:color,borderDownColor:'#ff1744',
        wickUpColor:color,wickDownColor:'#ff1744',
      });
      series.setData(data);
      chart.timeScale().fitContent();
      const ro=new ResizeObserver(()=>{if(ref.current)chart.applyOptions({width:ref.current.offsetWidth});});
      ro.observe(ref.current);
      return()=>{ro.disconnect();try{chart.remove();}catch{}};
    });
    return()=>{try{if(chart)chart.remove();}catch{}};
  },[data,color]);
  return <div ref={ref} style={{width:'100%',height:160,borderRadius:4,overflow:'hidden'}}/>;
}
