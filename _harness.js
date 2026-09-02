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
  const n=String(name);
  if(n==="/api/me")return {ok:true,json:async()=>({pro:true,email:"harness@test"}),text:async()=>""};
  if(String(n)==="perf.csv"){
    // 24 months: founders (two tickers) double while spy adds 20%; a third
    // ticker enters late and must join without distorting the base
    let rows="ticker,month,close\n";
    const m=i=>`20${23+Math.floor(i/12)}-${String(i%12+1).padStart(2,"0")}`;
    for(let i=0;i<24;i++){
      rows+=`SPY,${m(i)},${(100*Math.pow(1.2,i/23)).toFixed(4)}\n`;
      for(const tk of ["FA","FB","FC","FD","FE"])
        rows+=`${tk},${m(i)},${(50*Math.pow(2,i/23)).toFixed(4)}\n`;
      if(i>=12)rows+=`LATE,${m(i)},${(10*Math.pow(2,(i-12)/11)).toFixed(4)}\n`;
    }
    return {ok:true,text:async()=>rows};
  }
  if(n.startsWith("/pro/")){
    const f=n.replace("/pro/","");
    const t=require("fs").readFileSync("./"+f,"utf8");
    return {ok:true,text:async()=>t};
  }
  const p="./"+name;
  if(!fs.existsSync(p))throw new Error("missing "+name);
  const t=fs.readFileSync(p,"utf8");
  return {ok:true,text:async()=>t};
};

const html=fs.readFileSync("index.html","utf8");
const js=html.match(/<script>([\s\S]*)<\/script>/)[1];
const runPage=new Function(js+"\n;return {get state(){return state},get EVENTS(){return EVENTS},loadData,renderActivity,evFiltered,evValCell,evPctCell,evTable,openDrawer,money,sortTape,renderFeed,sellKind,evBase,syncChips,toggleDir,toggleKind,setKind,trajStats,tjLens,soldTickers,renderTrends,chartBlock,cleanHist,renderBars,renderTable,fInfo,perfSeries,perfWindow,renderPerf,get PERF(){return PERF},get HIST(){return HIST},set HIST(v){HIST=v},get PANEL(){return PANEL},set PANEL(v){PANEL=v},get FOUNDERS(){return FOUNDERS},set FOUNDERS(v){FOUNDERS=v},EVSAMPLE};");
const P=runPage();

(async()=>{
  await P.loadData();
  const {state,EVENTS,renderActivity,evFiltered,evValCell,evPctCell,evTable,openDrawer,money,sortTape,toggleDir,toggleKind}=P;
  const assert=(c,m)=>{if(!c){console.error("FAIL:",m);process.exit(1);}console.log("ok:",m);};

  assert(state.live.panel && state.live.events, "panel + events loaded live (history.csv not in zip: hist="+state.live.hist+")");
  assert(EVENTS.length>12000, "events loaded: "+EVENTS.length);

  // free view: THE SEAL IS THE ONLY GATE -- the free feed is the full
  // instrument over the free tier's companies, no sample, no lock
  state.pro=false; renderActivity();
  const freeHtml=els["#actwrap"]._html;
  assert(!freeHtml.includes("FREE — EVERY PURCHASE"), "no purchase-sample teaser in the free feed");
  assert(!freeHtml.includes("locked"), "no lock in the free feed");
  assert(freeHtml.includes("efoot")||freeHtml.includes("purchase"), "the free feed is the full table");
  const idxsrc=require("fs").readFileSync("index.html","utf8");
  // the seal is the only gate: no section may toggle features by tier
  assert(!idxsrc.includes('classList.toggle("gated",!state.pro)'),
    "no section gates its controls by tier");
  assert(idxsrc.includes('classList.add("hide")')&&idxsrc.includes('id="tjgate"'),
    "the old gate covers exist but stay hidden");
  assert(!/class="blurred"/.test(freeHtml), "the old blur treatment is gone");
  // NVDA has history in the free files: its chart renders open for
  // everyone -- free lacks companies, never features
  assert(P.chartBlock("NVDA").includes("chartbox")||P.chartBlock("NVDA").includes("No trajectory"),
    "a free reader gets the real chart when the data is theirs");
  assert(!freeHtml.includes("One row per filing"), "the methodology note is gone");
  assert(els["#actspot"]._html.includes("Buying")&&els["#actspot"]._html.includes("Selling down"), "both spotlight rows render");

  // pro view, default window
  state.pro=true; renderActivity();
  let proHtml=els["#actwrap"]._html;
  assert(proHtml.includes("escroll"), "pro feed renders");
  const evs90=evFiltered();
  assert(evs90.length>200 && evs90.length<2000, "90d window plausible: "+evs90.length);

  // every chip is independent; nothing selects or clears anything else
  const reset=()=>{state.ev.dir="";state.ev.kinds=[];};
  reset();
  const total=evFiltered().length;
  assert(total>200,"nothing selected shows everything: "+total);

  toggleDir("buys");
  assert(evFiltered().every(e=>e.c==="P"),"Bought alone: "+evFiltered().length);
  toggleDir("buys");
  assert(evFiltered().length===total,"clicking Bought again clears it");

  // the reported bug, both directions of it:
  toggleDir("sells");
  toggleKind("disc");
  assert(state.ev.dir==="sells"&&state.ev.kinds.includes("disc"),
    "Sold stays lit when Discretionary narrows it");
  assert(evFiltered().every(e=>P.sellKind(e)==="disc"),
    "and the feed is discretionary sales: "+evFiltered().length);
  reset();
  toggleKind("disc");
  assert(state.ev.dir==="","Discretionary alone does NOT light Sold — the reader moves the chips");
  assert(evFiltered().every(e=>P.sellKind(e)==="disc"),
    "Discretionary alone shows discretionary trades of both directions");

  // Bought + Discretionary is a real view now: buys carry their manner
  toggleDir("buys");
  assert(state.ev.dir==="buys"&&state.ev.kinds.includes("disc"),
    "Bought and Discretionary can both be on");
  const discBuys=evFiltered();
  assert(discBuys.length>0&&discBuys.every(e=>e.c==="P"&&e.pl==="discretionary"),
    "and together they return the discretionary purchases — the rows' own label, now filterable");

  // a combination that is REALLY empty stays an honest empty, not a repair
  toggleKind("disc");toggleKind("exsell");
  assert(evFiltered().length===0,
    "Bought + Options-cashed is empty by definition — exercise-and-sell is a sale");
  P.renderFeed();
  const emptyHtml=els["#actwrap"]._html;
  assert(emptyHtml.includes("escroll")&&emptyHtml.includes("eempty"),
    "the empty result keeps the table frame, message inside it");
  toggleKind("exsell");
  assert(emptyHtml.includes("<thead"),"and the column heads stay");
  reset();

  // manner is multi-select and the three manners partition Sold
  toggleKind("disc");toggleKind("plan");
  const both=evFiltered();
  assert(both.every(e=>["disc","plan"].includes(P.sellKind(e))),
    "Discretionary + Planned combine: "+both.length);
  reset();
  toggleDir("sells");
  const sells=evFiltered().length;
  let tally=0;
  for(const k of ["disc","plan","exsell"]){
    state.ev.kinds=[k];tally+=evFiltered().length;
  }
  assert(tally===sells,"the three manners partition Sold exactly ("+sells+")");
  assert(!(state.ev.kinds=["disc"],evFiltered()).some(e=>e.lb==="exercise and sell"),
    "compensation never files under Discretionary");
  reset();

  // the window no longer reaches the full decade
  state.ev.win="365";
  const yr=evFiltered();
  assert(yr.length<EVENTS.length&&yr.length>500,"twelve months is the widest window: "+yr.length);
  assert(!yr.some(e=>e.c==="S"&&P.sellKind(e)==="unknown"),
    "and inside it every sale is classified — the checkbox exists after April 2023");
  state.ev.win="90";

  // the Nadella decimal-shift error must not top the value sort
  state.ev.sort={key:"v",dir:-1}; const top=evFiltered()[0];
  assert(!top.fl, "largest-value sort excludes flagged prices (top: "+top.tk+" "+money(top.v)+")");
  const msft=EVENTS.find(e=>e.tk==="MSFT"&&e.td==="2020-09-01"&&e.fl);
  assert(msft && msft.fl, "the $189bn filer error is flagged");
  assert(evValCell(msft).includes("⚠"), "and shown with a caution, as filed");

  // pct blowups render capped
  const tko=EVENTS.find(e=>e.tk==="TKO"&&e.pc>100);
  assert(tko && evPctCell(tko).includes("≥100%"), "13,111% renders as ≥100%");

  // exercise-and-sell renders as unchanged
  const exs=EVENTS.find(e=>e.lb==="exercise and sell");
  assert(evPctCell(exs).includes("unchanged"), "exercise-and-sell shows stake unchanged");

  // search
  state.ev.win="365"; state.ev.sort={key:"fd",dir:-1}; state.ev.q="musk";
  const musk=evFiltered();
  assert(musk.length>0 && musk.every(e=>e.tk==="TSLA"), "search by surname reaches Musk: "+musk.length);
  state.ev.win="90";
  state.ev.q="";

  // sorting is by column head now
  P.sortTape("v"); assert(state.ev.sort.key==="v"&&state.ev.sort.dir===-1,"first click on a number head sorts descending");
  P.sortTape("v"); assert(state.ev.sort.dir===1,"second click flips it");
  P.sortTape("co"); assert(state.ev.sort.key==="co"&&state.ev.sort.dir===1,"a text head starts ascending");
  const alpha=evFiltered(); assert(alpha[0].tk<=alpha[alpha.length-1].tk,"company sort is alphabetical");
  P.sortTape("pc"); const bypc=evFiltered();
  assert(bypc[0].pc>=(bypc[50].pc||0),"share-of-stake sorts high to low");
  state.ev.sort={key:"fd",dir:-1};

  // money() must not print a thousand million
  assert(money(999959042)==="$1B","999,959,042 reads as $1B, not $1000M");
  assert(money(2.5e6)==="$2.5M"&&money(4.5e9)==="$4.5B","the ordinary cases still read right");

  // one card per person
  const spotHtml=els["#actspot"]._html;
  const names=[...spotHtml.matchAll(/class="who">([^<]+)</g)].map(m=>m[1]);
  assert(names.length===10,"ten cards, five per row");
  const buyNames=names.slice(0,5), sellNames=names.slice(5);
  assert(new Set(buyNames).size===5,"no chief executive twice in the buy row: "+buyNames.join(", "));
  assert(new Set(sellNames).size===5,"nor in the sell row: "+sellNames.join(", "));
  assert((spotHtml.match(/class="stk/g)||[]).length===10,"every card states its share of stake, or says why it cannot");
  assert(spotHtml.includes("partnership units rather than issued stock"),
    "and the Blackstone case explains itself on hover");
  const amts=[...spotHtml.matchAll(/class="amt">([^<]+)</g)].map(m=>m[1]);
  assert(amts.every(a=>/[MB]$/.test(a)),"every card is a trade of real size: "+amts.join(", "));
  assert((spotHtml.match(/class="spot sell"/g)||[]).length===5,"the sell row is styled as sales");
  assert(!spotHtml.includes("EX &amp; SELL")&&!/unchanged/.test(spotHtml),
    "no exercise-and-sell reaches the sell row");

  // the badge is a filter
  const badgeRow=evTable(evFiltered().slice(0,5),true);
  assert(/setKind\('(plan|disc|exsell|buys)'\)/.test(badgeRow),"a row badge filters to its own kind");

  // feed table markup for a real slice
  const t=evTable(evFiltered().slice(0,50),true);
  assert(t.includes("openDrawer(") && t.includes("sec.gov"), "rows are doors and carry filing links");
  assert(t.includes("sortTape('v')"), "the value head is clickable");

  // drawer with events present
  openDrawer("TSLA");
  assert(els["#drawer"]._html.includes("Latest trades"), "drawer prefers filed events");

  // spotlight picks are purchases with clean prices
  const spot=els["#actspot"]._html;
  assert(!spot.includes("⚠"), "neither row features a flagged price");

  // ---- trajectories ----
  // synthetic history: up, down, a fresh record low, and a zero-led record
  const day=n=>new Date(Date.now()-n*86400e3).toISOString().slice(0,10);
  P.HIST={
    UPX:[[day(1400),5.0,100],[day(700),6.2,120],[day(30),9.1,150]],
    DNX:[[day(1400),12.0,900],[day(700),10.0,800],[day(5),7.5,600]],
    LOWX:[[day(1500),8.0,500],[day(900),6.0,400],[day(400),5.0,350],[day(3),4.2,300]],
    ZLED:[[day(1500),0,0],[day(1000),3.0,100],[day(500),2.0,80],[day(2),1.5,60]],
  };
  const fakePanel=[["UPX","Upward Inc","A Founder"],["DNX","Downward Inc","B Exec"],
                   ["LOWX","Lowpoint Inc","C Exec"],["ZLED","Zeroled Inc","D Exec"]]
    .map(([tk,co,ceo])=>({tk,co,ceo,pct:5,sh:1,out:1}));
  P.PANEL=fakePanel;
  state.tjf=false;state.thoriz="";
  const up=P.tjLens("up"),down=P.tjLens("down"),low=P.tjLens("low");
  assert(up.some(x=>x.r.tk==="UPX")&&!up.some(x=>x.r.tk==="DNX"),
    "Accumulating finds the riser: "+up.map(x=>x.r.tk).join(","));
  assert(down.some(x=>x.r.tk==="DNX")&&!down.some(x=>x.r.tk==="UPX"),
    "Selling down finds the faller: "+down.map(x=>x.r.tk).join(","));
  assert(low.some(x=>x.r.tk==="LOWX"),"At new lows finds the fresh low");
  assert(low.some(x=>x.r.tk==="ZLED"),
    "a record that opens at zero can still set a real low");
  assert(!low.some(x=>x.r.tk==="UPX"),"a riser is not at a low");
  const st=P.trajStats("UPX",null);
  assert(Math.abs(st.d-4.1)<1e-9,"since-start delta is in percentage points: +"+st.d.toFixed(1));
  const st1=P.trajStats("UPX",365);
  assert(Math.abs(st1.d-(9.1-6.2))<1e-9,"the horizon baseline forward-fills: +"+st1.d.toFixed(1));

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
    for(const tk in P.PERF){if(tk!=="SPY")pinned[tk]={f:"yes",ev:"",src:""};}
    P.FOUNDERS=pinned;
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
    assert((svg.match(/<path /g)||[]).length===2,"two lines drawn");
    assert(svg.includes("Founders index")&&svg.includes("S&amp;P 500 (SPY)"),
      "end labels name the lines, not a dollar figure first");
    assert(P.state.pw==="60","a five-year record defaults to the 5-year preset, max chip hidden");
    assert(els["#perfnote"]._html.includes("portrait, not a strategy"),
      "the caveat ships with the chart");
    P.FOUNDERS=savedF;
  }

  // ---- founders-only, per section, independently ----
  {
    P.PANEL=[{tk:"TSLA",ceo:"Elon Musk",co:"Tesla",pct:29.9,val:9e11},
             {tk:"AAPL",ceo:"Tim Cook",co:"Apple",pct:0.02,val:1e9},
             {tk:"NVDA",ceo:"Jensen Huang",co:"NVIDIA",pct:3.5,val:1e11}];
    P.state.lbF=true;P.renderBars();
    const bars=els["#bars"]._html;
    const shown=[...bars.matchAll(/openDrawer\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    const allF=shown.length&&shown.every(tk=>{const i=P.fInfo(tk);return i&&i.f==="yes";});
    assert(allF,"founders-only leaderboard shows only proxy-named founders: "+shown.join(","));
    assert(els["#boardtitle"]._text&&els["#boardtitle"]._text.includes("founder"),
      "and the heading says so: "+els["#boardtitle"]._text);
    P.state.lbF=false;P.renderBars();
    const again=[...els["#bars"]._html.matchAll(/openDrawer\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    assert(again.length>shown.length,"toggling off restores the full board");
    assert(P.state.ev.f===false&&P.state.tjF===false&&P.state.tbF===false,
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
  const hold=P.tjLens("hold");
  assert(hold.every(x=>!P.soldTickers().has(x.r.tk)),
    "Never sold excludes anyone with a stake-reducing sale ("+hold.length+")");

  // ---- the trust layer ----
  const idx=require("fs").readFileSync("index.html","utf8");
  assert((idx.match(/about\.html/g)||[]).length>=2,
    "the About page is reachable from the nav and the footer");
  const about=require("fs").readFileSync("about.html","utf8");
  for(const t of ["Not investment advice","source of truth","One person",
                  "options","the 10-Q","10-K","survivorship bias",
                  "corrections@founderledequities.com","hello@founderledequities.com",
                  "Get in touch"])
    assert(about.includes(t),"about.html carries: "+t);
  assert(about.includes('href="./"'),"and links back to the site");
  assert(about.indexOf("Who makes this")<about.indexOf("How the numbers are made"),
    "who makes this comes before the method");
  assert(about.indexOf("Get in touch")<about.indexOf("The fine print"),
    "and contact sits just before the fine print");

  // ---- payments wiring on the page ----
  assert(idx.includes('href="/api/checkout"')&&idx.includes("$5/month"),
    "the Pro modal sells the real thing at the real price");
  assert(!idx.includes("Notify%20me%20when%20Pro%20opens"),"the waitlist CTA is gone");
  assert(!idx.includes("pro=1/.test"),"?pro=1 no longer grants anything");
  assert(idx.includes('"/api/me"')&&idx.includes('"/pro/events.csv"')&&idx.includes('"events-free.csv"'),
    "data loading is session-aware with free fallbacks");
  assert(idx.includes("function signIn")&&idx.includes("/api/portal"),
    "sign-in and the account portal are reachable");
  assert(idx.includes('og:title')&&idx.includes('twitter:card')&&idx.includes('rel="canonical"'),
    "a pasted link unfurls as a card");
  assert(idx.includes("mailto:hello@founderledequities.com?subject=Refund"),
    "the refund promise carries its address");
  assert(idx.includes("Latest filing")&&idx.includes("EVENTS.reduce"),
    "the header dates the newest filing read, not the newest that moved a stake");
  const terms=require("fs").readFileSync("terms.html","utf8");
  for(const t of ["$5 per month","7 days","hello@founderledequities.com","not investment advice"])
    assert(terms.toLowerCase().includes(t.toLowerCase()),"terms.html carries: "+t);

  // ---- the free file: every S&P event, the seal is the only gate ----
  {
    const freeCsv=require("fs").readFileSync("events-free.csv","utf8");
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

  console.log("\nALL RENDER PATHS PASS");
})().catch(e=>{console.error("HARNESS ERROR:",e);process.exit(1);});
