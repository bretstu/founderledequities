// Executes the page's inline script against the real CSVs with a DOM shim,
// then walks every render path. Not a pixel test -- a "does the logic run
// and produce sane markup" test.
const fs = require("fs");

function el(id){
  return {
    id, _html:"", _text:"", _cls:new Set(),
    set innerHTML(v){this._html=v;}, get innerHTML(){return this._html;},
    set textContent(v){this._text=v;}, get textContent(){return this._text;},
    classList:{
      toggle(c,f){}, add(c){el._last=el._last||{};el._last[id]=c;}, remove(c){}, contains(c){return false;}
    },
    addEventListener(){}, setAttribute(){}, querySelector(){return el(id+">q");},
    querySelectorAll(){return [];},
    style:{}, dataset:{},
  };
}
const els={};
global.document={
  querySelector:s=>els[s]||(els[s]=el(s)),
  querySelectorAll:s=>[],
  addEventListener(){},
  body:{style:{}},
};
global.window={scrollY:0, scrollTo(){}, };
global.location={search:"", hash:""};
global.requestAnimationFrame=f=>f();
global.fetch=async(name)=>{
  const n=String(name).replace(/\?v=[^&]*$/,"");   // the data version key the page appends
  if(n==="/api/me")return {ok:true,json:async()=>({pro:true,email:"harness@test"}),text:async()=>""};
  if(String(n)==="perf.csv"){
    // 24 months: founders (two tickers) double while spy adds 20%; a third
    // ticker enters late and must join without distorting the base
    let rows="ticker,month,close\n";
    const m=i=>`20${23+Math.floor(i/12)}-${String(i%12+1).padStart(2,"0")}`;
    for(let i=0;i<24;i++){
      rows+=`SPY,${m(i)},${(100*Math.pow(1.2,i/23)).toFixed(4)}\n`;
      rows+=`RSP,${m(i)},${(100*Math.pow(1.1,i/23)).toFixed(4)}\n`;
      for(const tk of ["FA","FB","FC","FD","FE"])
        rows+=`${tk},${m(i)},${(50*Math.pow(2,i/23)).toFixed(4)}\n`;
      if(i>=12)rows+=`LATE,${m(i)},${(10*Math.pow(2,(i-12)/11)).toFixed(4)}\n`;
    }
    return {ok:true,text:async()=>rows};
  }
  // THE SERVED FILES FIRST. site-data/ is what deploy.sh publishes -- the
  // free files cut by the S&P list at its root, the full ones under pro/ --
  // so the harness reads the tiers the site actually serves when they
  // exist, and the root files (a fixture folder) otherwise.
  // THE NEWEST COPY, NOT THE FIRST. site-data/ is written by deploy.sh, so
  // between a rebuild of events.csv and the next deploy it is the previous
  // deploy's file; run in that gap, the harness judged a stale copy of the
  // data it was meant to guard and blocked the deploy that would have
  // refreshed it (v34's shifted columns sat in site-data/ through v35 and
  // v36). Whichever candidate was written last is the one under test.
  const first=(...cands)=>{
    const have=cands.filter(c=>fs.existsSync(c));
    if(!have.length)return null;
    return have.sort((a,b)=>fs.statSync(b).mtimeMs-fs.statSync(a).mtimeMs)[0];
  };
  if(n.startsWith("/pro/")){
    const f=n.replace("/pro/","");
    const p=first("./site-data/pro/"+f,"./site-data/"+f,"./"+f);
    if(!p)throw new Error("missing "+n);
    return {ok:true,text:async()=>fs.readFileSync(p,"utf8")};
  }
  const p=first("./site-data/"+n,"./"+n);
  if(!p)throw new Error("missing "+name);
  const t=fs.readFileSync(p,"utf8");
  return {ok:true,text:async()=>t};
};

const html=fs.readFileSync("index.html","utf8");
const js=html.match(/<script>([\s\S]*)<\/script>/)[1];
const runPage=new Function(js+"\n;return {get state(){return state},get EVENTS(){return EVENTS},set EVENTS(v){EVENTS=v},loadData,evBadge,unchangedKind,pctOf,SEAL,renderActivity,evValCell,evPctCell,openCompany,money,sellKind,evSide,setWin,actWindow,actRows,actSorted,actStats,tapeKind,tapeManner,soldTickers,lastTrades,exportTable,cleanHist,renderTable,setScreen,fInfo,set TAPE_LIMIT(v){TAPE_LIMIT=v},get SCREEN_COUNTS(){return SCREEN_COUNTS},set SCREEN_COUNTS(v){SCREEN_COUNTS=v},get HIST(){return HIST},set HIST(v){HIST=v},get PANEL(){return PANEL},set PANEL(v){PANEL=v},get FOUNDERS(){return FOUNDERS},set FOUNDERS(v){FOUNDERS=v},EVSAMPLE};");
const P=runPage();

(async()=>{
  await P.loadData();
  const {state,EVENTS,renderActivity,evValCell,evPctCell,openCompany,money,setWin,actWindow,actRows,actSorted,tapeKind}=P;
  const assert=(c,m)=>{if(!c){console.error("FAIL:",m);process.exit(1);}console.log("ok:",m);};
  const idxsrc=require("fs").readFileSync("index.html","utf8");

  assert(state.live.panel && state.live.events, "panel + events loaded live (history.csv not in zip: hist="+state.live.hist+")");
  assert(EVENTS.length>12000, "events loaded: "+EVENTS.length);

  // ---- the seal is the only gate ----
  state.pro=false; renderActivity();
  assert(!idxsrc.includes('classList.toggle("gated",!state.pro)'),
    "no section gates its controls by tier");
  assert(!idxsrc.includes('id="tjgate"')&&!idxsrc.includes('id="trends"'),
    "the Trajectories section is gone");
  // ONE LIST, TWO DEPTHS (PLAN.md section 5): the home page is the hero, what
  // they own now (the screener's table at twenty rows), this week's tape,
  // the footer. No board of bars, no index chart, no second copy of the list.
  assert(idxsrc.indexOf('class="hero"')<idxsrc.indexOf('id="table"')&&idxsrc.indexOf('id="table"')<idxsrc.indexOf('id="activity"')&&idxsrc.indexOf('id="activity"')<idxsrc.indexOf('<footer>'),
    "sections run hero, what they own now, the tape, footer");
  assert(!idxsrc.includes('id="board"')&&!idxsrc.includes('id="perfsec"')&&!idxsrc.includes('id="bars"')&&!idxsrc.includes("function renderBars(")&&!idxsrc.includes("function perfSeries("),
    "the bars and the index chart are gone from the page (the chart is a static image on Method)");
  assert(idxsrc.includes('class="tablesec home"')&&idxsrc.includes("let TABLE_LIMIT=10;")&&idxsrc.includes('<a class="exit" href="/companies/">All companies'),
    "the home table is a ten-row preview with the rest a click away");
  assert(idxsrc.includes('<h2>What they own now</h2>')&&!idxsrc.includes("The wealthiest CEOs"),"the heading is the question, not a rich list");
  assert(idxsrc.includes('<a href="/tape/">Tape</a>')&&idxsrc.includes('<a href="/companies/">Companies</a>')&&!idxsrc.includes('>Scoreboard<')&&!idxsrc.includes('>Performance<'),
    "the nav is Tape · Companies · Method · Pro");
  assert(!/class="blurred"/.test(els["#actwrap"]._html),"no blur class from the old gate anywhere: a sealed figure is a data-shape placeholder");

  // ---- THE TAPE: a weather line, the controls, one table grouped by kind ----
  {
    assert(idxsrc.includes('id="actwin"')&&idxsrc.includes('data-win="7"')&&idxsrc.includes('data-win="365"'),"the window chips run 7d to 12m");
    assert(!idxsrc.includes('id="actcards"')&&!idxsrc.includes('id="actkinds"')&&!idxsrc.includes('id="actsort"'),"no card grid, no kind or sort chips: the table is the tape");
    assert(idxsrc.includes('id="tg-f"')&&idxsrc.includes('id="tg-buys"')&&idxsrc.includes('id="tg-nocomp"'),"three toggles: founders only, open-market buys, hide compensation");
    assert(/id="tg-f" checked/.test(idxsrc),"founders only is on by default");
    state.pro=true; setWin(365); state.ev.f=false; state.ev.buys=false; state.ev.nocomp=false; renderActivity();
    const rows=actSorted(actRows());
    // THE HOME PAGE IS AN EXCERPT: twelve rows, the full tape a click away
    assert(idxsrc.includes("let TAPE_LIMIT=8;")&&idxsrc.includes('class="activitysec excerpt"'),"the home page's tape is an eight-row excerpt");
    assert((els["#actwrap"]._html.match(/class="dayrow/g)||[]).length===8&&/^8 of [\d,]+ filings/.test(els["#actnote"]._html),"eight rows, and the note says of how many: "+els["#actnote"]._html.slice(0,40));
    assert(idxsrc.includes('<a class="exit" href="/tape/">The full tape &rarr;</a>')&&idxsrc.includes('<a class="exit" href="/companies/">All companies &rarr;</a>'),"both previews exit the same way: heading left, the full page right");
    assert(idxsrc.includes('id="homesub"'),"the letter's signup sits under the tape excerpt");
    P.TAPE_LIMIT=0;
    assert(rows.length>50,"the window holds the year's filings: "+rows.length);
    // kind groups in order: bought, discretionary, plan, compensation
    const order={bought:0,disc:1,plan:2,comp:3};
    const ks=rows.map(e=>order[tapeKind(e)]);
    assert(ks.every((k,i)=>i===0||k>=ks[i-1]),"kind groups in the tape's order");
    assert(ks.includes(0)&&ks.includes(1)&&ks.includes(2)&&ks.includes(3),"all four kinds present in a year");
    // ranked by the stake's move within a group
    const mv=e=>{const p=P.pctOf(e);if(!p||e.mk)return null;return e.c==="P"?Math.max(0,p.v):Math.max(0,-p.v);};
    for(const k of [0,1,2]){const g=rows.filter(e=>order[tapeKind(e)]===k).map(mv).filter(x=>x!==null);assert(g.every((x,i)=>i===0||x<=g[i-1]),"ranked by the stake's move within kind "+k);}
    const html=els["#actwrap"]._html;
    renderActivity();
    assert(els["#actwrap"]._html.includes('class="tape"')&&(els["#actwrap"]._html.match(/class="dayrow/g)||[]).length===rows.length,"one table row per filing, once the excerpt's limit is lifted");
    assert(/<th>Kind<\/th><th>Company<\/th><th>CEO<\/th><th class="n">Amount<\/th><th class="n">New stake<\/th><th>Manner<\/th><th>Traded<\/th>/.test(html),"the seven columns, in order: the date is its own");
    assert(html.includes("openCompany(")&&html.includes("sec.gov"),"rows are doors and the amount links to the filing");
    assert(!html.includes("DISCRET."),"kinds are spelled out");
    const stats=els["#actstats"]._html;
    assert(/<b>\d+<\/b> CEOs? bought · (<b>\d+<\/b> for the first time ever · )?<b>\d+<\/b> cut a stake · <b>\d+<\/b> sold on a plan · <b>\d+<\/b> compensation filings? did not move a stake/.test(stats),"the weather line: "+stats.replace(/<[^>]+>/g,""));
    // a plan is never counted as a cut; compensation never as a cut
    const cut=+(stats.match(/<b>(\d+)<\/b> cut a stake/)||[])[1];
    const discPeople=new Set(actWindow().filter(e=>tapeKind(e)==="disc").map(e=>e.tk+"|"+e.ceo)).size;
    assert(cut===discPeople,"'cut a stake' counts discretionary sellers only: "+cut+" vs "+discPeople);
    // toggles
    state.ev.buys=true; renderActivity(); assert(actRows().every(e=>tapeKind(e)==="bought"),"open-market buys only");
    state.ev.buys=false; state.ev.nocomp=true; renderActivity(); assert(actRows().every(e=>tapeKind(e)!=="comp"),"hide compensation hides it");
    state.ev.nocomp=false;
    // the subhead names the window's dates
    assert(/last 12 months, [A-Z][a-z]{2} \d+ to [A-Z][a-z]{2} \d+/.test(els["#tapesub"]._text||""),"the subhead names the dates: "+els["#tapesub"]._text);
    // a free reader: 7d only, the longer chips dimmed and gated, the Pro note under the chips
    state.pro=false; setWin(7); renderActivity();
    assert(state.ev.win==="7","7 days for a free reader");
    // openPro is a page now (/pro/); in the harness location is a stub, so the gate is judged by the window not changing
    setWin(30); assert(state.ev.win==="7","a longer window is gated for a free reader and does not change the window");
    assert((els["#pronote"]._html||"").includes("Pro"),"the Pro note sits under the chips");
    state.pro=true; setWin(365);
  }

  // ---- a sealed filing: the amount shows, the stake after is blurred ----
  {
    const savedE=P.EVENTS;
    P.EVENTS=savedE.concat([{tk:"ZZSEAL",ceo:"Sealed Person",c:"S",lb:"discretionary sale",pl:"discretionary",sh:null,v:1.5e6,fd:"2026-09-01",td:"2026-08-31",pc:null,po:null,ha:null,nc:null,rs:null,u:"",mk:true}]);
    state.ev.f=false; setWin(365); renderActivity();
    const html=els["#actwrap"]._html; const row=html.slice(html.indexOf("ZZSEAL"),html.indexOf("ZZSEAL")+900);
    assert(row.includes("$1.5M"),"the amount is the Form 4's own number and shows on a sealed row");
    assert((row.match(/class="sealed"/g)||[]).length===1,"and the stake after the trade is the one blur");
    assert(!row.includes("sec.gov"),"no filing link on a sealed row");
    assert((els["#actnote"]._html||"").includes("outside the S&P 500"),"the note says where the sealed stakes are");
    P.EVENTS=savedE; renderActivity();
  }

  // ---- the first-ever purchase ----
  {
    const savedE=P.EVENTS;
    P.EVENTS=[{tk:"NEWB",ceo:"First Timer",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:5e5,fd:"2026-09-03",td:"2026-09-02",pc:2.5,po:41.0,ha:41000,nc:1000,rs:null,u:"https://www.sec.gov/x",fb:true},
              {tk:"OLDB",ceo:"Old Hand",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:9e5,fd:"2026-09-03",td:"2026-09-02",pc:0.1,po:1.0,ha:1e6,nc:1000,rs:null,u:"https://www.sec.gov/y",fb:false}];
    state.ev.f=false; setWin(30); renderActivity();
    assert(els["#actstats"]._html.includes("<b>1</b> for the first time ever"),"the weather line counts first-ever purchases");
    assert(els["#actwrap"]._html.includes('class="firstb"'),"and the row carries the tag");
    P.EVENTS=savedE; setWin(365); renderActivity();
  }

  // ---- the free screener says how much of the answer is sealed ----
  {
    const savedP=P.PANEL, savedC=P.SCREEN_COUNTS;
    P.PANEL=[{tk:"AAA",co:"A",ceo:"a",pct:12,val:1e9,masked:false,conf:"high",asof:"2026-09-01",rp:1,rv:1},
             {tk:"BBB",co:"B",ceo:"b",pct:null,val:null,masked:true,conf:"",asof:"",rp:2,rv:2}];
    P.SCREEN_COUNTS={m0f0h0:2,m10f0h0:2,m5f0h0:2,m1f0h0:2,m0f1h0:1,m10f1h0:1,m5f1h0:1,m1f1h0:1,m0f0h1:2,m10f0h1:2,m5f0h1:2,m1f0h1:2,m0f1h1:1,m10f1h1:1,m5f1h1:1,m1f1h1:1};
    P.state.pro=false;P.state.min=10;P.state.q="";P.state.tbF=false;P.state.tbH=false;P.renderTable();
    assert((els["#tcount"]._html||"").includes("1 more match in Pro"),"under >10% the sealed match is counted: "+els["#tcount"]._html);
    P.state.q="AAA";P.renderTable();
    assert(!(els["#tcount"]._html||"").includes("more match"),"under a search there is no count");
    P.state.q="";P.state.min=0;P.PANEL=savedP;P.SCREEN_COUNTS=savedC;P.renderTable();
  }

  // ---- the named screens: four questions, each a predicate the build also counts ----
  {
    const savedP=P.PANEL,savedC=P.SCREEN_COUNTS,savedL=P.state.screen;
    P.PANEL=[{tk:"NS",co:"Never",ceo:"a",pct:12,val:1,masked:false,conf:"high",asof:"2026-09-01",fd:true},
             {tk:"HI",co:"Hired",ceo:"b",pct:0.3,val:1,masked:false,conf:"high",asof:"2026-09-01",fd:false},
             {tk:"SL",co:"Sealed",ceo:"c",pct:null,val:null,masked:true,conf:"",asof:"",fd:true,rp:1,rv:1}];
    P.SCREEN_COUNTS={"s:over-10":3,"s:hired-under-1":2};
    P.TABLE_LIMIT=0;P.state.pro=false;
    P.setScreen("over-10");
    const rowsOf=()=>[...els["#tbody"]._html.matchAll(/<tr onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
    let tks=rowsOf();
    assert(tks.length===1&&tks[0]==="NS","over-10 keeps the one who owns more than a tenth; a sealed row cannot be judged: "+JSON.stringify(tks));
    assert((els["#tcount"]._html||"").includes("2 more match in Pro"),"and the count says how many more match in Pro: "+els["#tcount"]._html);
    P.setScreen("hired-under-1");
    tks=rowsOf();
    assert(tks.length===1&&tks[0]==="HI","hired under 1% keeps the hired CEO with the small stake");
    assert(P.state.tbF===false&&P.state.min===0,"a screen is the whole question: the other filters reset");
    P.setScreen("");P.PANEL=savedP;P.SCREEN_COUNTS=savedC;P.state.screen=savedL;P.TABLE_LIMIT=20;P.renderTable();
  }

  // ---- the screener: three-year change, last trade, never sold ----
  const day=n=>new Date(Date.now()-n*86400e3).toISOString().slice(0,10);
  P.HIST={
    UPX:[[day(1400),5.0,100],[day(700),6.2,120],[day(30),9.1,150]],
    DNX:[[day(1400),12.0,900],[day(700),10.0,800],[day(5),7.5,600]],
    NOH:[[day(10),3.0,10]],
  };
  const fakePanel=[["UPX","Upward Inc","A Founder"],["DNX","Downward Inc","B Exec"],["NOH","Newlisted Inc","C Exec"]]
    .map(([tk,co,ceo])=>({tk,co,ceo,pct:5,sh:1,out:1,val:1e9,conf:"high"}));
  const savedPanel=P.PANEL,savedEvents=P.EVENTS,savedF0=P.FOUNDERS;
  P.PANEL=fakePanel;P.FOUNDERS={UPX:{f:"yes",ev:"founded it",src:"x"}};
  P.EVENTS=[{tk:"DNX",ceo:"B Exec",c:"S",lb:"discretionary sale",pl:"discretionary",fd:day(5),td:day(6),sh:100,v:1e6,pc:1,ha:600,nc:-100,rs:0,u:"https://sec.gov/x"},
            {tk:"UPX",ceo:"A Founder",c:"P",lb:"open-market purchase",pl:"discretionary",fd:day(30),td:day(31),sh:30,v:3e5,pc:2,ha:150,nc:30,rs:0,u:"https://sec.gov/y"},
            {tk:"UPX",ceo:"A Founder",c:"S",lb:"exercise and sell",pl:"plan",fd:day(2),td:day(2),sh:5,v:1e4,pc:null,ha:150,nc:0,rs:0,u:""}];
  for(const r of P.PANEL){r.r1=r.tk==="UPX"?41.2:r.tk==="DNX"?-12.5:null;}   /* the 1-yr return rides on the row (universe.csv: ret_1y) */
  state.q="";state.min=0;state.tbF=false;state.tbH=false;state.sort={key:"r1",dir:-1};
  P.renderTable();
  let tb=els["#tbody"]._html;
  const order=[...tb.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(order[0]==="UPX"&&order[1]==="DNX"&&order[2]==="NOH","sorted by 1-yr return: the riser, the faller, then the one with no year of prices: "+order.join(",")+" r1="+P.PANEL.map(r=>r.r1).join(","));
  assert(/UPX[\s\S]*?c-r1"><span class="up">\+41\.2%/.test(tb),"the riser reads +41.2% in green");
  assert(/DNX[\s\S]*?c-r1"><span class="down">-12\.5%/.test(tb),"the faller reads -12.5% in red");
  assert(!tb.includes('class="tbar"')&&!tb.includes("c-conf"),"no bar in the ownership cell, no confidence column: every cell is one value");
  assert(!tb.includes("pts"),"nobody is told about points");
  assert(!tb.includes('class="spark"'),"no chart preview in the screener -- the number says it, the company page draws it");
  assert(tb.includes('class="n num c-mc"'),"a market cap column");
  const rowOf=tk=>{const i=tb.indexOf(`onclick="openCompany('${tk}')"`);const j=tb.indexOf("</tr>",i);return tb.slice(i,j);};
  // NEVER SOLD IS A SWITCH, NOT A COLUMN: a claim you ask for, not one made about everyone
  assert(!tb.includes('class="nsy"')&&!tb.includes("c-ns"),"no never-sold column in the table");
  {P.state.tbH=true;P.renderTable();const on=els["#tbody"]._html;
   assert(on.includes("openCompany('UPX')")&&on.includes("openCompany('NOH')")&&!on.includes("openCompany('DNX')"),"the Never sold switch keeps the one who never reduced a stake and the short record, drops the seller -- options cashed don't count");
   P.state.tbH=false;P.renderTable();}
  assert(rowOf("DNX").includes('c-amt">$1M')&&/c-lt"><span class="kind (disc|plan)">(Discretionary|Planned)<\/span>/.test(rowOf("DNX")),"the last move is its kind (never Sold in red on a plan) and the amount sits in its own column: "+rowOf("DNX").slice(rowOf("DNX").indexOf("c-lt"),rowOf("DNX").indexOf("c-lt")+80));
  assert(!tb.includes('class="asof'),"as-of left the table for the company page and the export");
  assert(/c-lt"><span class="kind (disc|plan)">/.test(rowOf("DNX"))&&rowOf("UPX").includes('c-lt"><span class="kind bought">Bought')&&rowOf("UPX").includes('c-fd">Yes'),"the last trade that moved the stake, in words; the founder flag its own column");
  assert(rowOf("NOH").includes("no trade that moved the public-company stake"),"and an honest dash where there is none");
  state.tbH=true;P.renderTable();
  const held=[...els["#tbody"]._html.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(held.join(",")==="UPX,NOH","the Never sold switch keeps only those who never did: "+held.join(","));
  // the export: the rows as shown, every field, quoted where it must be
  const csv=P.exportTable();
  const hdr=csv.split("\n")[0];
  assert(hdr==="#,Company,Ticker,CEO,Founder,Ownership %,Value,Market cap,1-yr return %,Last move,Amount,Traded","the CSV is the table as shown, plus ticker and the founder flag as columns: "+hdr.slice(0,60));
  assert(csv.split("\n").length===3&&csv.includes("UPX")&&csv.includes("NOH")&&!csv.includes("DNX"),"and only the rows as filtered");
  assert(csv.split("\n")[1].split(",").length===hdr.split(",").length,"every row has every column");
  state.tbH=false;state.sort={key:"r1",dir:1};P.renderTable();
  const asc=[...els["#tbody"]._html.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(asc[0]==="DNX"&&asc[2]==="NOH","ascending puts the faller first and the short record still last");
  state.sort={key:"pct",dir:-1};
  P.PANEL=savedPanel;P.EVENTS=savedEvents;P.FOUNDERS=savedF0;
  // ---- the cleaned series: known lies out, real findings in ----
  P.HIST={
    ECHO:[["2023-12-21",59.47,49902472,"G",null,null,2687900],
          ["2023-12-31",17.46,47398278,"AFM",2352.94,95937688,-98441882],
          ["2024-04-01",54.00,146629004,"G",null,null,99230726],
          ["2024-06-24",53.71,145841315,"G",null,null,7563458],
          ["2026-07-29",50.67,147184017,"G",null,null,null]],
    HOODX:[["2021-07-28",0.0,0,"FMS",121119240,773677,null],
          ["2021-08-02",6.12,52358633,"ADJ",null,null,52358633],
          ["2022-11-01",5.98,52998563,"MS",341499.91,28264,null],
          ["2026-07-01",5.40,52998563,"MS",null,null,null]],
    REALX:[["2020-01-01",10.0,1000,"",null,null,null],
          ["2021-01-01",4.0,400,"S",600000,600,null],
          ["2022-01-01",9.0,900,"P",500000,500,null],
          ["2023-01-01",9.2,920,"",null,null,null]],
    // a Musk-shaped record: violent legitimate moves carrying big
    // unexplained noise that is NEVER reversed -- every point must survive
    MUSKX:[["2023-03-08",13.2,715e6,"M",49665,10500,null],
          ["2024-12-30",12.8,713e6,"G",null,-268000,null],
          ["2025-11-06",27.2,1137e6,"A",142e9,423.7e6,null],
          ["2026-04-21",22.9,1041e6,"",null,-96e6,null],
          ["2026-06-16",29.9,1123e6,"M",14.2e9,286.4e6,null]],
  };
  const ce=P.cleanHist("ECHO");
  assert(!ce.some(p=>p[1]===17.46),
    "the merger-day restated artifact is excluded (unexplained -98.4M mirrored by +99.2M)");
  assert(P.cleanHist("HOODX")[0][1]===6.12,
    "a record that opens at 0% opens at its first real holding instead");
  assert(P.cleanHist("REALX").some(p=>p[1]===4.0),
    "a genuine crash-and-recover (traded, not unexplained) is kept");
  assert(P.cleanHist("MUSKX").length===5,
    "violent moves with reconciled filings (unexplained empty, as Musk's really are) all survive");
  // the pipeline's restated column outranks the V-heuristic entirely
  // a stake above 100% is the denominator lagging a purchase of new issuance, and leaves the math
  P.HIST={SMMTX:[["2022-06-01",9.1,60e6,"",null,null,null,false],
                 ["2023-03-06",274.36,552e6,"P",395e6,376e6,null,false],
                 ["2024-01-02",78.81,552e6,"",null,null,null,false],
                 ["2026-06-12",76.47,610e6,"",null,null,null,false]]};
  const sm=P.cleanHist("SMMTX");
  assert(sm.length===3&&!sm.some(p=>p[1]>100),"a point above 100% is a known lie and leaves the cleaned series");
  P.HIST={COL:[["2020-01-01",2.0,2700000,"",null,null,null,false],
               ["2021-01-01",0.03,40000,"",null,null,-2660000,true],
               ["2021-01-05",0.031,42000,"",null,null,null,true],
               ["2021-02-01",2.01,2720000,"",null,null,2680000,false],
               ["2022-01-01",2.02,2730000,"",null,null,null,false]]};
  const cc=P.cleanHist("COL");
  assert(cc.length===3&&!cc.some(p=>p[1]<1),
    "a multi-row crater the pipeline marked is excluded whole: "+cc.map(p=>p[1]));

  // the sample-paint poisoning: swap HIST, and the cleaned view must follow
  P.cleanHist("ECHO");
  P.HIST={ECHO:[["2020-01-01",5,100,"",null,null,null],["2021-01-01",6,120,"",null,null,null]]};
  assert(P.cleanHist("ECHO").length===2&&P.cleanHist("ECHO")[0][1]===5,
    "replacing HIST invalidates the cleaned cache — no more sample ghosts");

  // ---- founders against the index: a static image on Method, drawn at deploy ----
  {
    const about=require("fs").readFileSync("about.html","utf8");
    assert(about.includes("<!--PERF_SVG-->")&&about.includes("Why founder-led")&&about.includes("A portrait, not a strategy."),
      "the chart's place is Method, with its caveat");
    assert(require("fs").existsSync("ops/perf_svg.py"),"and ops/perf_svg.py draws it");
  }

  // ---- founders-only, per section, independently ----
  {
    P.PANEL=[{tk:"TSLA",ceo:"Elon Musk",co:"Tesla",pct:29.9,val:9e11},
             {tk:"AAPL",ceo:"Tim Cook",co:"Apple",pct:0.02,val:1e9},
             {tk:"NVDA",ceo:"Jensen Huang",co:"NVIDIA",pct:3.5,val:1e11}];
    P.state.tbF=true;P.state.q="";P.state.min=0;P.renderTable();
    const shown=[...els["#tbody"]._html.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    const allF=shown.length&&shown.every(tk=>{const i=P.fInfo(tk);return i&&i.f==="yes";});
    assert(allF,"founders-only shows only proxy-named founders: "+shown.join(","));
    P.state.tbF=false;P.renderTable();
    const again=[...els["#tbody"]._html.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    assert(again.length>shown.length,"toggling off restores the full list");
    assert(P.state.ev.f===false&&P.state.tbH===false,"the table's switch moved no other section's");
  }

  // ---- buys have manners; units-structured stakes never read as zero ----
  {
    // a discretionary buy and a scheduled buy both carry their manner
    const disc={c:"P",pl:"discretionary",lb:"open-market purchase"};
    const plan={c:"P",pl:"plan",lb:"scheduled purchase"};
    const conv={c:"P",pl:"unknown",lb:"open-market purchase"};
    assert(P.sellKind(disc)==="disc"&&P.sellKind(plan)==="plan",
      "purchases carry their plan state into the manner chips");
    assert(P.sellKind(conv)==="unknown",
      "an unknown-plan conversion pseudo-buy matches no manner chip");
    assert(P.sellKind({c:"S",pl:"discretionary",lb:"exercise and sell"})==="exsell",
      "exercise-and-sell still outranks the checkbox, sales only");

    // Blackstone-shaped: operating partnership, no common
    const bx={tk:"BX",co:"Blackstone",ceo:"S. Schwarzman",pct:0.0,sh:0,val:1,units:true};
    const real={tk:"KKR",co:"KKR",ceo:"J. Bae",pct:2.1,sh:1e6,val:2e9,units:false};
    P.PANEL=[bx,real];
    P.renderTable();
    const table=els["#tbody"]._html;
    assert(table.includes("units")&&table.includes("partnership units"),
      "the table names the structure instead of printing 0.000%");
  }

  // never-sold consults the filed trades, not the history codes
  assert(P.soldTickers().has("TSLA"),"Musk has stake-reducing sales on record");
  {const s=P.soldTickers();const ex=EVENTS.find(e=>P.unchangedKind(e)!==null);
   if(ex&&!EVENTS.some(e=>e.tk===ex.tk&&e.c==="S"&&P.unchangedKind(e)===null))
     assert(!s.has(ex.tk),"a company whose only sales left the stake unchanged is not a seller: "+ex.tk);}

  // ---- the trust layer ----
  const idx=require("fs").readFileSync("index.html","utf8");
  assert((idx.match(/about\.html/g)||[]).length>=2,
    "the About page is reachable from the nav and the footer");
  const about=require("fs").readFileSync("about.html","utf8");
  // THE ABOUT PAGE IS THE METHOD, IN PLAIN LANGUAGE. What a reader must find there:
  for(const t of ["ownership = shares the CEO holds",              // the definition, as a formula
                  "shares the company has outstanding",
                  "Unvested restricted stock",                     // what counts, and what does not
                  "Options and restricted stock units",
                  "Partnership units",
                  "10-Q or 10-K",                                  // the denominator's source
                  "beneficial ownership",                          // why other numbers differ
                  "Voting power",
                  "The one exception",                             // remarks, read by a person
                  "Compensation",                                  // what the company gave and what was sold of it
                  "10b5-1",
                  "proxy statement decides",                       // who is a founder
                  "A portrait, not a strategy",                    // the index's caveat
                  "dividends excluded",
                  "RSP",
                  "high","medium","low",                           // the marks
                  "Nothing here is investment advice",
                  "One person",
                  "corrections@founderledequities.com","hello@founderledequities.com"])
    assert(about.includes(t),"about.html carries: "+t);
  assert(about.includes('href="./"'),"and links back to the site");
  assert(about.indexOf("How ownership is calculated")<about.indexOf("What counts as a trade")
       &&about.indexOf("What counts as a trade")<about.indexOf("The fine print"),
    "the method comes before the fine print");

  // ---- payments wiring on the page ----
  assert(idx.includes('href="/pro/"')&&idx.includes("$15 a month or $150 a year"),
    "the Pro box points at the plan page at the real price");
  const pro=require("fs").readFileSync("pro.html","utf8");
  assert(pro.includes('href="/api/checkout?plan=monthly"')&&pro.includes('href="/api/checkout?plan=yearly"')&&pro.includes("14-day trial"),
    "the plan page sells the real thing: two prices, a trial");
  assert(!idx.includes("Notify%20me%20when%20Pro%20opens"),"the waitlist CTA is gone");
  assert(!idx.includes("pro=1/.test"),"?pro=1 no longer grants anything");
  assert(idx.includes('"/api/me"')&&idx.includes('"/pro/events.csv"')&&idx.includes('"events-free.csv"'),
    "data loading is session-aware with free fallbacks");
  assert(idx.includes("function signIn")&&idx.includes('location.href="/account/"'),
    "sign-in is reachable and Account is the control panel (billing is a row on it)");
  const acct=require("fs").readFileSync("assets/account-page.js","utf8");
  assert(acct.includes("/api/portal")&&acct.includes("/api/letter")&&acct.includes("remove:true")&&acct.includes("/api/logout"),"the account page holds billing, the letter, the watches and sign out");
  assert(idx.includes('og:title')&&idx.includes('twitter:card')&&idx.includes('rel="canonical"'),
    "a pasted link unfurls as a card");
  {const head=idx.slice(0,idx.indexOf("</head>"));
   assert(head.includes('property="og:image" content="https://founderledequities.com/og.png"')&&head.includes('name="twitter:image"'),
     "a shared link unfurls with a picture");
   assert(require("fs").existsSync("ops/og_image.py")&&require("fs").readFileSync("ops/deploy.sh","utf8").includes("og_image.py"),
     "and the deploy draws it from tonight's numbers");
   assert(!/S&P 500 CEO ownership/.test(head)&&!/Every S&P 500 chief executive/.test(head),"the title and descriptions no longer describe an S&P-only site");
   assert(/2,100\+/.test(head),"and say how many companies the site covers");
   const box=idx.slice(idx.indexOf('id="promodal"'),idx.indexOf("</script>",idx.indexOf('id="promodal"')));
   assert(!box.includes("all 500 companies")&&box.includes('id="mcount"')&&box.includes("more companies"),
     "the Pro box sells the other companies, with the count filled from the data");
   assert(!about.includes("Until that page exists"),"About no longer promises a page that now exists");
   /* CEO wherever a reader scans; "chief executive" only inside About's prose */
   const visible=idx.replace(/<!--[\s\S]*?-->/g,"").replace(/\/\*[\s\S]*?\*\//g,"").replace(/^\s*\/\/.*$/gm,"");
   const labels=visible;
   assert(!/chief executive/i.test(labels),"no label on the page says chief executive: "+(labels.match(/.{0,40}chief executive.{0,40}/i)||[""])[0]);
   assert(idx.includes('<h1 id="thesis">What the person running the company still owns.</h1>'),"the hero says what the site is, the same for every reader");
   assert(!idx.includes('See what moved')&&!idx.includes('Go Pro &middot; $15/mo</a>')&&!idx.includes("herobtns"),"no buttons on the fold: the sentence is the door, Pro is the header's");
   assert(idx.includes('<p class="thisweek" id="thisweek"></p>')&&idx.includes('<a href="/tape/">${weekLine()}')&&idx.includes("sold without a plan"),"the week in one spoken sentence, and it is the link to the tape");
   assert(!idx.includes('<a href="/pro/">Pro</a>')&&!idx.includes("Weekly tape, free")&&!idx.includes("navwatches"),"the header is where you are: Tape · Companies · Method and one button");
   assert(idx.includes("Filings through ")&&!idx.includes("Latest filing read"),"the dates are the footer's, not the hero's");
   assert(idx.includes("the last twelve months are open. Everything else is Pro."),"the copy rule's one-line form under the doors");
   assert(idx.includes('id="thisweek"')&&idx.includes("function weekLine("),"the week in one line under the hero");

   assert(idx.includes('"CEOs own more than 5%"')&&idx.includes('"S&P 500 CEOs own more than 5%"'),"the rarity is the strip's first cell: a known denominator or none");
   assert(head.includes("what every CEO owns")&&idx.includes("CEOs own more than 5%")&&idx.includes('data-key="ceo">CEO<'),"the title, the strip and the screener say CEO");}
  assert(require("fs").readFileSync("pro.html","utf8").includes("mailto:hello@founderledequities.com?subject=Refund"),
    "the refund promise carries its address, on the plan page");
  assert(idx.includes('"/api/hit"')&&idx.includes("fle_nohit")&&idx.includes('hit("view","page")'),
    "the page counts its own visitors, and the owner can switch it off");
  assert(!idx.includes("document.cookie"),"and sets no cookie to do it");
  assert(about.includes("without cookies"),"About says so");
  assert(idx.includes("Filings through")&&idx.includes("EVENTS.reduce"),
    "the footer dates the newest filing read, not the newest that moved a stake");
  const terms=require("fs").readFileSync("terms.html","utf8");
  for(const t of ["$15 per month","$150 per year","14-day trial","7 days","hello@founderledequities.com","not investment advice"])
    assert(terms.toLowerCase().includes(t.toLowerCase()),"terms.html carries: "+t);

  // ---- the free file: every S&P event, the seal is the only gate ----
  {
    const freeCsv=require("fs").readFileSync(require("fs").existsSync("site-data/events-free.csv")?"site-data/events-free.csv":"events-free.csv","utf8");
    const lines=freeCsv.trim().split("\n");
    const head=lines[0].split(",");
    const iCode=head.indexOf("code");
    let buys=0,sells=0;
    for(const l of lines.slice(1)){
      const c=l.split(",");
      if(c[iCode]==="P")buys++;
      else if(c[iCode]==="S")sells++;
    }
    assert(buys>500,"the free file keeps every purchase: "+buys);
    assert(sells>100,"and every sale — free means the whole S&P record: "+sells);
  }


  // ---- ONE FOUNDERS TOGGLE FOR THE WHOLE TAPE ----
  {
  const savedE=P.EVENTS,savedF=P.FOUNDERS;
  P.FOUNDERS={FND:{f:"yes",ev:"co-founded",src:"x"},HIRE:{f:"no",ev:"",src:"x"}};
  P.EVENTS=[
    {tk:"FND",ceo:"A Founder",c:"S",lb:"sale",pl:"plan",sh:100,v:1e6,fd:"2026-09-02",td:"2026-09-01",pc:-10,po:5,ha:1000,nc:-100,rs:null},
    {tk:"HIRE",ceo:"A Hire",c:"S",lb:"sale",pl:"discretionary",sh:100,v:5e6,fd:"2026-09-02",td:"2026-09-01",pc:-20,po:1,ha:1000,nc:-100,rs:null},
    {tk:"HIRE",ceo:"A Hire",c:"S",lb:"exercise and sell",pl:"plan",sh:10,v:2e5,fd:"2026-09-02",td:"2026-09-01",pc:null,po:1,ha:1000,nc:0,rs:null},
  ];
  P.state.pro=true;P.state.ev.f=false;setWin(30);renderActivity();
  const off=els["#actwrap"]._html;
  assert(off.includes("A Founder")&&off.includes("A Hire"),"toggle off: every CEO");
  assert(els["#actstats"]._html.includes("<b>1</b> cut a stake")&&els["#actstats"]._html.includes("<b>1</b> sold on a plan"),"the weather line counts the discretionary seller as a cut and the planned one as a plan");
  P.state.ev.f=true;renderActivity();
  const on=els["#actwrap"]._html;
  assert(on.includes("A Founder")&&!on.includes("A Hire"),"toggle on: founders only");
  assert((els["#tapesub"]._text||"").startsWith("Founders only"),"and the subhead says so");
  P.state.ev.f=true;P.EVENTS=savedE;P.FOUNDERS=savedF;setWin(365);renderActivity();
}

  console.log("\nALL RENDER PATHS PASS");
})().catch(e=>{console.error("HARNESS ERROR:",e);process.exit(1);});

