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
      toggle(c,f){}, add(c){}, remove(c){}, contains(c){return false;}
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
const runPage=new Function(js+"\n;return {get state(){return state},get EVENTS(){return EVENTS},set EVENTS(v){EVENTS=v},loadData,evBadge,unchangedKind,pctOf,SEAL,renderActivity,evValCell,evPctCell,openCompany,money,sellKind,evSide,setKind,setWin,setSort,actWindow,actRows,actSorted,actStats,actCards,trajStats,soldTickers,sparkline,lastTrades,exportTable,cleanHist,renderBars,renderTable,fInfo,perfSeries,perfWindow,perfChart,renderPerf,perfReturns,perfBins,distChart,renderDist,distCrown,distPanel,get PERF(){return PERF},get HIST(){return HIST},set HIST(v){HIST=v},get PANEL(){return PANEL},set PANEL(v){PANEL=v},get FOUNDERS(){return FOUNDERS},set FOUNDERS(v){FOUNDERS=v},EVSAMPLE};");
const P=runPage();

(async()=>{
  await P.loadData();
  const {state,EVENTS,renderActivity,evValCell,evPctCell,openCompany,money,setWin,setKind,setSort,actWindow,actRows,actSorted}=P;
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
  // the product first (leaderboard, activity, screener); the argument last
  assert(idxsrc.indexOf('id="activity"')<idxsrc.indexOf('id="table"')&&idxsrc.indexOf('id="table"')<idxsrc.indexOf('id="perfsec"'),
    "sections run leaderboard, activity, table, performance");
  assert(idxsrc.indexOf('href="#activity"')<idxsrc.indexOf('href="#perfsec"'),"and the nav follows the page");
  assert(!/class="blurred"/.test(els["#actwrap"]._html),"no blur class from the old gate anywhere: a sealed figure is a data-shape placeholder");

  // ---- RECENT ACTIVITY: one table, ranked by what moved the stake ----
  {
    // the section is one dataset at one zoom: a window, a founders switch,
    // a counts line, three cards, a kind chip row, a sort, one table
    assert(idxsrc.includes('id="actwin"')&&idxsrc.includes('data-win="7"')&&idxsrc.includes('data-win="365"'),"the window chips run 7 days to 12 months");
    assert(!idxsrc.includes('id="actcols"')&&!idxsrc.includes('id="actday"')&&!idxsrc.includes('id="acttable"'),"the day strip, the two columns and the drawer are gone");
    setWin(365); setKind("all");
    const rows=actSorted(actRows());
    assert(rows.length>50,"the window holds the year's stake-moving trades: "+rows.length);
    assert(rows.every(e=>P.evSide(e)!=="exsell"),"All is purchases and sales that moved a stake; compensation is its own chip");
    // the default sort is by stake change, largest move first, sealed rows last
    const pcs=rows.filter(e=>!e.mk).map(e=>{const p=P.pctOf(e);if(!p)return null;return e.c==="P"?Math.max(0,p.v):Math.max(0,-p.v);});
    const ranked=pcs.filter(x=>x!==null);
    assert(ranked.length>10&&ranked.every((x,i)=>i===0||x<=ranked[i-1]),"sorted by stake change, largest first");
    const firstSealed=rows.findIndex(e=>e.mk), lastOpen=rows.map(e=>!e.mk).lastIndexOf(true);
    assert(firstSealed===-1||firstSealed>lastOpen,"a sealed row has no figure to rank by and follows the ranked rows");
    const html=els["#actwrap"]._html;
    assert(html.includes('class="daytab"')&&(html.match(/class="dayrow"/g)||[]).length===rows.length,"one table row per filing, seven columns");
    assert(/<th>Kind<\/th><th>Company<\/th><th class="n">Value<\/th><th class="n">Stake<\/th><th>Manner<\/th><th>Transaction<\/th><th>Filing<\/th>/.test(html),"the columns, in order");
    assert(html.includes("openCompany(")&&html.includes("sec.gov"),"rows are doors and carry filing links");
    // the counts line and the three cards
    const stats=els["#actstats"]._html;
    assert(/<b>\d+<\/b> CEOs? bought · <b>\d+<\/b> cut a stake/.test(stats),"the counts line says who bought and who cut: "+stats.replace(/<[^>]+>/g,""));
    const cards=els["#actcards"]._html;
    assert((cards.match(/class="acard"/g)||[]).length===4&&cards.includes("Largest buy")&&cards.includes("Biggest add")&&cards.includes("Largest sale")&&cards.includes("Biggest cut"),"four cards: largest buy, biggest add, largest sale, biggest cut");
    const adds=rows.filter(e=>e.c==="P"&&!e.mk).map(e=>[e,P.pctOf(e)]).filter(x=>x[1]&&x[1].v>0);
    if(adds.length){const top=adds.reduce((a,b)=>b[1].v>a[1].v?b:a)[0];assert(cards.includes(`openCompany('${top.tk}')`),"the biggest add card is the purchase that added most to a stake: "+top.tk);}
    const buys=rows.filter(e=>e.c==="P"&&!e.mk&&!e.fl&&e.v);
    if(buys.length){const top=buys.reduce((a,b)=>(b.v||0)>(a.v||0)?b:a);assert(cards.includes(`openCompany('${top.tk}')`),"the largest buy card is the largest purchase by value: "+top.tk);}
    const sales=rows.filter(e=>e.c==="S"&&!e.mk&&!e.fl&&e.v);
    if(sales.length){const top=sales.reduce((a,b)=>(b.v||0)>(a.v||0)?b:a);assert(cards.includes(`openCompany('${top.tk}')`),"the largest sale card is the largest sale by value: "+top.tk);}
    const cuts=rows.filter(e=>e.c==="S"&&!e.mk).map(e=>[e,P.pctOf(e)]).filter(x=>x[1]&&x[1].v<0);
    if(cuts.length){const top=cuts.reduce((a,b)=>b[1].v<a[1].v?b:a)[0];assert(cards.includes(`openCompany('${top.tk}')`),"the biggest cut card is the largest reduction of a stake, not the largest sale: "+top.tk);}
    // the kind chips narrow; the sort chips reorder
    setKind("buys"); assert(actRows().every(e=>e.c==="P"),"Bought is purchases only");
    setKind("sells"); assert(actRows().every(e=>e.c==="S"&&P.unchangedKind(e)===null),"Sold is sales that reduced the stake");
    setKind("comp"); assert(actRows().every(e=>P.unchangedKind(e)!==null),"Compensation is the kept-apart trades");
    setKind("all"); setSort("v");
    const byV=actSorted(actRows()).filter(e=>!e.mk).map(e=>e.fl?0:(e.v||0));
    assert(byV.every((x,i)=>i===0||x<=byV[i-1]),"sorted by value, largest first");
    setSort("fd");
    const byD=actSorted(actRows()).map(e=>e.fd);
    assert(byD.every((x,i)=>i===0||x<=byD[i-1]),"sorted by date, newest first, sealed rows interleaved");
    setSort("pc"); setWin(7);
    assert(actWindow().every(e=>Date.now()-Date.parse(e.fd+"T00:00:00Z")<=8*86400e3),"the 7-day window is seven days");
    // the note under the table says what was shown and where the rest is
    assert(/\d[\d,]* filings? in the last 7 days/.test(els["#actnote"]._html),"the note counts the rows of the window");
    setWin(365);
  }

  // ---- a sealed filing is a row with its figures blurred ----
  {
    const savedE=P.EVENTS;
    P.EVENTS=savedE.concat([{tk:"ZZSEAL",ceo:"Sealed Person",c:"S",lb:"discretionary sale",pl:"discretionary",sh:null,v:null,fd:"2026-09-01",td:"2026-08-31",pc:null,ha:null,nc:null,rs:null,u:"",mk:true}]);
    setWin(365); setKind("all"); renderActivity();
    const html=els["#actwrap"]._html;
    const row=html.slice(html.indexOf("ZZSEAL"));
    assert(row.includes('class="sealed"')&&(row.slice(0,900).match(/class="sealed"/g)||[]).length===2,"a sealed row blurs its value and its stake change, and nothing else");
    assert(!row.slice(0,900).includes("sec.gov"),"and carries no filing link");
    assert(els["#actnote"]._html.includes("from sealed companies"),"the note says how many rows are sealed");
    P.EVENTS=savedE; renderActivity();
  }

  // ---- the first-ever purchase ----
  {
    const savedE=P.EVENTS;
    P.EVENTS=[{tk:"NEWB",ceo:"First Timer",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:5e5,fd:"2026-09-03",td:"2026-09-02",pc:2.5,ha:41000,nc:1000,rs:null,u:"https://www.sec.gov/x",fb:true},
              {tk:"OLDB",ceo:"Old Hand",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:9e5,fd:"2026-09-03",td:"2026-09-02",pc:0.1,ha:1e6,nc:1000,rs:null,u:"https://www.sec.gov/y",fb:false}];
    setWin(30); setKind("all"); renderActivity();
    assert(els["#actstats"]._html.includes("<b>1</b> bought for the first time ever"),"the counts line counts first-ever purchases");
    assert(els["#actcards"]._html.includes("Largest buy")&&els["#actcards"]._html.includes("openCompany('OLDB')"),"the largest buy card is by value");
    assert(els["#actwrap"]._html.includes('class="firstb"'),"and the row carries the tag");
    P.EVENTS=savedE; setWin(365); renderActivity();
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
  assert(rowOf("DNX").includes('c-amt">$1M')&&rowOf("DNX").includes('c-lt"><span class="down">Sold</span>'),"the last trade and its amount sit in their own columns");
  assert(!tb.includes('class="asof'),"as-of left the table for the company page and the export");
  assert(rowOf("DNX").includes('c-lt"><span class="down">Sold')&&rowOf("UPX").includes('c-lt"><span class="up">Bought')&&rowOf("UPX").includes('c-fd">Yes'),"the last trade that moved the stake, in words; the founder flag its own column");
  assert(rowOf("NOH").includes("no trade that moved the public-company stake"),"and an honest dash where there is none");
  state.tbH=true;P.renderTable();
  const held=[...els["#tbody"]._html.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(held.join(",")==="UPX,NOH","the Never sold switch keeps only those who never did: "+held.join(","));
  // the export: the rows as shown, every field, quoted where it must be
  const csv=P.exportTable();
  const hdr=csv.split("\n")[0];
  assert(hdr==="#,Company,Ticker,CEO,Founder,Ownership %,Value,Market cap,1-yr return %,Last trade,Type,Amount,Traded","the CSV is the table as shown, plus ticker and the founder flag as columns: "+hdr.slice(0,60));
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
  assert(P.trajStats("ECHO",null).atLow===true,
    "and with the false floor gone, Ergen's true record low is finally visible");
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
  assert(Math.abs(P.trajStats("SMMTX",1095).d-(76.47-78.81))<1e-9||P.trajStats("SMMTX",1095).base<=100,
    "and the three-year change is measured from the next real point");
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

  // ---- founders against the index ----
  {
    // the cohort is perf INTERSECT live founder labels now; the fixture
    // must pin its own labels or real founders.csv rows (some explicitly
    // "no") evict fixture tickers and shift the >=5-names start
    const savedF=P.FOUNDERS;
    const pinned={};
    for(const tk in P.PERF){if(tk!=="SPY"&&tk!=="RSP")pinned[tk]={f:"yes",ev:"",src:""};}
    P.FOUNDERS=pinned;
    P.state.pc="all";   /* the existing checks are about the whole cohort */
    const full=P.perfSeries();
    assert(full&&full.months.length===24,"perf chains all 24 months: "+(full&&full.months.length));
    const endF=full.founders[full.founders.length-1],endS=full.spy[full.spy.length-1];
    // five doubling founders alone would land at $200; the late entrant
    // (a faster doubler joining at month 13) lifts the average above it --
    // entering companies participate, exactly as the note says
    assert(endF>20300&&endF<22500,"the late entrant lifts an otherwise-doubled index: $"+endF.toFixed(0));
    // and remove the late entrant to prove the clean double
    const late=P.PERF.LATE;delete P.PERF.LATE;
    const bare=P.perfSeries();
    assert(Math.abs(bare.founders[bare.founders.length-1]-20000)<200,
      "without it, five identical doublers double $10,000 to $"+bare.founders[bare.founders.length-1].toFixed(0));
    P.PERF.LATE=late;
    assert(Math.abs(endS-12000)<150,"and SPY grows its 20%: $"+endS.toFixed(0));
    const w=P.perfWindow(full,"12");
    assert(w.months.length===13&&Math.abs(w.founders[0]-10000)<1e-6,
      "a window rebases both lines to $10,000 at its own start");
    P.renderPerf();
    const svg=els["#perfchart"]._html;
    assert((svg.match(/<path /g)||[]).length===3,"three lines drawn: founders, SPY, RSP");
    assert(svg.includes("Founders index")&&svg.includes("S&amp;P 500 (SPY)"),
      "end labels name the lines, not a dollar figure first");
    assert(P.state.pw==="60","a five-year record defaults to the 5-year preset, max chip hidden");
    // ---- inside the index: the distribution behind the line ----
    {const d=P.perfWindow(full,"12");
     const dist=P.perfReturns(d);
     assert(dist.items.length>=5&&dist.items.every(i=>typeof i.ret==="number"),"a return per constituent with a close at both ends of the window");
     assert(Math.abs(dist.spy-10)<1,"and the benchmark's own return over the same window (half its two-year 20%): "+dist.spy);
     assert(Math.abs(P.perfReturns(full).spy-20)<1,"over the whole record, the benchmark's full 20%");
     {const late=dist.items.find(i=>i.tk==="LATE");
      assert(late&&late.since&&late.since>dist.from,"the late entrant is placed, measured from the month it joined: since "+(late&&late.since));
      assert(typeof late.spyOwn==="number","and judged against the S&P over the same months");
      assert(dist.joined===1&&dist.skipped===0,"nothing that fed the line is missing from the bins");
      assert(dist.items.filter(i=>!i.since).every(i=>i.spyOwn===null||Math.abs(i.spyOwn-dist.spy)<1e-9),"a full-window company is judged against the full-window S&P");}
     const {svg,bins,tint}=P.distChart(dist,P.perfBins("12"));
     assert((svg.match(/rx="2" fill="rgba/g)||[]).length===dist.items.length,"one tile per company (hit areas and axis boxes are not tiles)");
     {const crownedN=bins.reduce((n,b)=>n+Math.min(3,b.items.length),0);
      assert((svg.match(/<a href="\/company\//g)||[]).length===crownedN,"only a named tile is a link; a block is part of the column");}
     assert(svg.includes("S&amp;P 500 +10%"),"the benchmark is marked where it lands");
     assert(svg.includes(">below<")&&svg.includes(">above<")&&svg.includes(">-40% to<")&&svg.includes(">0% to<")&&svg.includes(">+40%<"),"a labelled box under every column says its range");
     {const boxes=(svg.match(/<rect x="[^"]+" y="[^"]+" width="[^"]+" height="34" rx="3" fill="(rgba[^"]+)"/g)||[]);
      assert(boxes.length===13,"one box per column");
      const tiles=[...svg.matchAll(/<rect x="([^"]+)" y="[^"]+" width="[^"]+" height="[^"]+" rx="2" fill="(rgba[^"]+)"/g)];
      const byX={};for(const m of tiles)byX[m[1]]=m[2];
      const boxX=[...svg.matchAll(/<rect x="([^"]+)" y="[^"]+" width="[^"]+" height="34" rx="3" fill="(rgba[^"]+)"/g)];
      assert(boxX.every(m=>!(m[1] in byX)||byX[m[1]]===m[2]),"each box wears exactly its column's tint");}
     assert((svg.match(/class="hit"/g)||[]).length===P.perfBins("12").length+1,"every column is a door, not just the number above it");
     // the crowns: up to three named tiles at the top of every column, chosen by stake
     {const crowned=(svg.match(/class="crown"/g)||[]).length;
      const expect=bins.reduce((n,b)=>n+Math.min(3,b.items.length),0);
      assert(crowned===expect,"three crowned tiles per column, or all of a small bin: "+crowned+" vs "+expect);
      const many={items:[],spy:10,from:dist.from,end:dist.end,skipped:0};
      for(let k=0;k<120;k++)many.items.push({tk:"T"+k,ret:1+k*0.05});   /* all in the 0..+10% bin */
      const big=P.distChart(many,P.perfBins("12"));
      assert((big.svg.match(/class="crown"/g)||[]).length===3,"a hundred-deep bin still shows exactly three names");
      assert((big.svg.match(/rx="2" fill="rgba/g)||[]).length===120&&(big.svg.match(/<a href="\/company\//g)||[]).length===3,"every one of the hundred is a tile; only the three named ones are links");
      // the panel: the bucket by name, sorted by return, every one a door
      const full=big.bins.find(b=>b.items.length===120);
      const panel=P.distPanel(full,big.bins.indexOf(full),big.tint);
      assert((panel.match(/class="dtile"/g)||[]).length===120,"the panel names everyone in the bucket");
      assert(panel.includes("120 companies")&&!panel.includes("Open these in the screener"),"with the count; the panel is the drill-down, there is no hand-off");
      const order=[...panel.matchAll(/<b>(T\d+)<\/b>/g)].map(m=>m[1]);
      assert(order[0]==="T0"&&order[119]==="T119","sorted by return, lowest first");
      // a bin that ends at zero is a loss: red, not green
      const z=P.perfBins("12").indexOf(0);
      const tints=[...svg.matchAll(/height="34" rx="3" fill="(rgba\((\d+)[^)]*\))"/g)].map(m=>m[2]);
      assert(tints[z]==="194"&&tints[z+1]==="11","the -10% to 0% box is red and the 0% to +10% box is green");}
     els["#perfdist"]=els["#perfdist"]||el("#perfdist");
     P.renderDist(d);
     {const h=els["#perfdist"]._html;
      assert(h.includes('class="disth"')&&h.indexOf('class="disth"')<h.indexOf("<svg"),"a title above the histogram");
      assert(h.includes("beat the S&amp;P 500 over the same months")&&h.indexOf("distsub")<h.indexOf("<svg"),"one line of context above it");
      assert(h.includes('class="distkey"')&&h.indexOf("distkey")>h.indexOf("</svg>"),"legend and notes below it");
      assert(h.includes("joined the index during the window")&&h.includes('class="dot"'),"the legend explains the dot");
      assert(!h.includes("too recently"),"no 'too recently' bucket: every constituent is in a bin");
      assert(/<circle /.test(h),"an entrant's tile is marked with a dot");}
     // the bins scale with the window
     assert([P.perfBins("12"),P.perfBins("36"),P.perfBins("60")].every(e=>e.length===12),"thirteen columns on every window");
     assert(P.perfBins("12").slice(-1)[0]===100&&P.perfBins("36").slice(-1)[0]===300&&P.perfBins("60").slice(-1)[0]===500,"each window's edges spaced for its moves");
     P.state.sort={key:"pct",dir:-1};}
    // ---- the cohort toggle: a choice, the same for every reader ----
    {const savedPanel3=P.PANEL;
     /* the five long-lived founders are S&P members; the late entrant is not */
     /* injected rows go FIRST: a real panel may already hold FE (FirstEnergy), and find() must hit the test row */
     P.PANEL=[...["FA","FB","FC","FD","FE"].map(tk=>({tk,co:tk,ceo:"a",pct:5,sh:1,out:1,val:1,conf:"high",sp:true})),...savedPanel3];
     P.state.pc="sp";const sp=P.perfSeries();
     assert(sp&&sp.count===5,"S&P 500 founders: only the cohort's S&P members: "+(sp&&sp.count));
     P.state.pc="all";const al=P.perfSeries();
     assert(al.count>sp.count,"All founder-led: the whole cohort: "+al.count);
     assert(al.rsp&&Math.abs(al.rsp[al.rsp.length-1]-11000)<150,"the equal-weight S&P rides along as a third line: $"+al.rsp[al.rsp.length-1].toFixed(0));
     const svg3=P.perfChart(al);
     assert(svg3.includes("S&amp;P equal weight (RSP)")&&svg3.includes("stroke-dasharray"),"drawn dashed and labelled");
     P.renderPerf();
     assert(/Founders -?[\d.]+%\/yr/.test(els["#perfnote"]._html)&&els["#perfnote"]._html.includes("S&amp;P 500 equal weight")&&els["#perfnote"]._html.includes('href="about.html"'),"the note under the chart is the returns, the caveat, and the method linkly and names both benchmarks");
     assert(els["#perfsub"]._html.includes("all ")||els["#perfsub"].textContent.includes("all "),"the subtitle names the cohort");
     P.state.pc="sp";P.renderPerf();
     assert((els["#perfsub"].textContent||els["#perfsub"]._html).includes("in the S&P 500"),"and says S&P 500 when that is the cohort");
     assert(P.state._perfFull&&P.state._perfFull.count===al.count,"but the screener's return column still covers the whole cohort: "+P.state._perfFull.count);
     P.state.pc="all";P.PANEL=savedPanel3;P.renderPerf();}
    assert(String(els["#perfsub"]._text||els["#perfsub"]._html||"").includes("survivors only"),
      "the caveat ships with the chart, in its caption");
    P.FOUNDERS=savedF;
  }

  // ---- founders-only, per section, independently ----
  {
    P.PANEL=[{tk:"TSLA",ceo:"Elon Musk",co:"Tesla",pct:29.9,val:9e11},
             {tk:"AAPL",ceo:"Tim Cook",co:"Apple",pct:0.02,val:1e9},
             {tk:"NVDA",ceo:"Jensen Huang",co:"NVIDIA",pct:3.5,val:1e11}];
    P.state.lbF=true;P.renderBars();
    const bars=els["#bars"]._html;
    const shown=[...bars.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    const allF=shown.length&&shown.every(tk=>{const i=P.fInfo(tk);return i&&i.f==="yes";});
    assert(allF,"founders-only leaderboard shows only proxy-named founders: "+shown.join(","));
    assert(els["#boardtitle"]._text&&els["#boardtitle"]._text.includes("founder"),
      "and the heading says so: "+els["#boardtitle"]._text);
    P.state.lbF=false;P.renderBars();
    const again=[...els["#bars"]._html.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    assert(again.length>shown.length,"toggling off restores the full board");
    assert(P.state.ev.f===false&&P.state.tbF===false&&P.state.tbH===false,
      "the leaderboard switch moved no other section's");
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
    P.renderBars();
    const board=els["#bars"]._html;
    assert(!board.includes("'BX'")&&board.includes("'KKR'"),
      "a units-structured stake does not rank on the common-stock board");
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
  assert(idx.includes('href="/api/checkout"')&&idx.includes("$5 a month"),
    "the Pro modal sells the real thing at the real price");
  assert(!idx.includes("Notify%20me%20when%20Pro%20opens"),"the waitlist CTA is gone");
  assert(!idx.includes("pro=1/.test"),"?pro=1 no longer grants anything");
  assert(idx.includes('"/api/me"')&&idx.includes('"/pro/events.csv"')&&idx.includes('"events-free.csv"'),
    "data loading is session-aware with free fallbacks");
  assert(idx.includes("function signIn")&&idx.includes("/api/portal"),
    "sign-in and the account portal are reachable");
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
   assert(idx.includes('<h1 id="thesis">What every <b>CEO</b> owns of the company they run.</h1>'),"the hero says what the site is, the same for every reader");
   assert(idx.includes('"CEOs own more than 5%"')&&idx.includes('"S&P 500 CEOs own more than 5%"'),"the rarity is the strip's first cell: a known denominator or none");
   assert(head.includes("what every CEO owns")&&idx.includes("The wealthiest CEOs")&&idx.includes('data-key="ceo">CEO<'),"the title, the board and the screener say CEO");}
  assert(idx.includes("mailto:hello@founderledequities.com?subject=Refund"),
    "the refund promise carries its address");
  assert(idx.includes('"/api/hit"')&&idx.includes("fle_nohit")&&idx.includes('hit("view","page")'),
    "the page counts its own visitors, and the owner can switch it off");
  assert(!idx.includes("document.cookie"),"and sets no cookie to do it");
  assert(about.includes("without cookies"),"About says so");
  assert(idx.includes("Latest filing")&&idx.includes("EVENTS.reduce"),
    "the header dates the newest filing read, not the newest that moved a stake");
  const terms=require("fs").readFileSync("terms.html","utf8");
  for(const t of ["$5 per month","7 days","hello@founderledequities.com","not investment advice"])
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


  // ---- ONE FOUNDERS SWITCH FOR THE WHOLE ACTIVITY SECTION ----
  {
  const savedE=P.EVENTS,savedF=P.FOUNDERS;
  P.FOUNDERS={FND:{f:"yes",ev:"co-founded",src:"x"},HIRE:{f:"no",ev:"",src:"x"}};
  P.EVENTS=[
    {tk:"FND",ceo:"A Founder",c:"S",lb:"sale",pl:"plan",sh:100,v:1e6,fd:"2026-09-02",td:"2026-09-01",pc:10,ha:1000,nc:-100,rs:null},
    {tk:"HIRE",ceo:"A Hire",c:"S",lb:"sale",pl:"discretionary",sh:100,v:5e6,fd:"2026-09-02",td:"2026-09-01",pc:20,ha:1000,nc:-100,rs:null},
    {tk:"HIRE",ceo:"A Hire",c:"S",lb:"exercise and sell",pl:"plan",sh:10,v:2e5,fd:"2026-09-02",td:"2026-09-01",pc:null,ha:1000,nc:0,rs:null},
  ];
  P.state.ev.f=false;setWin(30);setKind("all");renderActivity();
  const off=els["#actwrap"]._html;
  assert(off.includes("A Founder")&&off.includes("A Hire"),"switch off: the table lists every CEO's stake-moving trade");
  assert(els["#actstats"]._html.includes("<b>2</b> cut a stake"),"and the counts line counts both");
  P.state.ev.f=true;renderActivity();
  const on=els["#actwrap"]._html;
  assert(on.includes("A Founder")&&!on.includes("A Hire"),"switch on: the table is founders only");
  assert(els["#actstats"]._html.includes("<b>1</b> cut a stake"),"the counts line counts founders only");
  assert(!els["#actnote"]._html.includes("compensation trade"),"and the compensation line does not count a hired CEO's options cashed");
  const shead=require("fs").readFileSync("index.html","utf8");
  assert(/<div class="shead">\s*<h2>Recent activity<\/h2>[\s\S]{0,900}id="evf"/.test(shead)&&(shead.match(/id="evf"/g)||[]).length===1,"the one switch sits in the section's head");
  P.state.ev.f=false;P.EVENTS=savedE;P.FOUNDERS=savedF;setWin(365);renderActivity();
}

  console.log("\nALL RENDER PATHS PASS");
})().catch(e=>{console.error("HARNESS ERROR:",e);process.exit(1);});

