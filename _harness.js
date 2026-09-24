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
  // THE SERVED FILES FIRST. site-data/ is what deploy.sh publishes -- one
  // tree, every number in it (the tiers left with the paid version,
  // 2026-09-23) -- so the harness reads what the site actually serves when
  // it exists, and the root files (a fixture folder) otherwise.
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
  const p=first("./site-data/"+n,"./"+n);
  if(!p)throw new Error("missing "+name);
  const t=fs.readFileSync(p,"utf8");
  return {ok:true,text:async()=>t};
};

const html=fs.readFileSync("index.html","utf8");
const js=html.match(/<script>([\s\S]*)<\/script>/)[1];
const runPage=new Function(js+"\n;return {get state(){return state},get EVENTS(){return EVENTS},set EVENTS(v){EVENTS=v},loadData,evBadge,unchangedKind,pctOf,renderActivity,evValCell,evPctCell,openCompany,money,sellKind,evSide,setWin,actWindow,actRows,actRow,actSorted,actStats,setTapeSort,tapeHead,tapeKind,tapeGroup,tapeDetail,tapeManner,evMove,evMoved,evDim,moveWhy,setKind,setMoved,tapeCounts,soldTickers,lastTrades,exportTable,cleanHist,renderTable,setScreen,setGroup,passes,presetOf,screenSentence,DEFAULTS,PRESETS,fInfo,set TAPE_LIMIT(v){TAPE_LIMIT=v},get SCREEN_COUNTS(){return SCREEN_COUNTS},set SCREEN_COUNTS(v){SCREEN_COUNTS=v},get HIST(){return HIST},set HIST(v){HIST=v},get PANEL(){return PANEL},set PANEL(v){PANEL=v},get FOUNDERS(){return FOUNDERS},set FOUNDERS(v){FOUNDERS=v},EVSAMPLE};");
const P=runPage();

(async()=>{
  await P.loadData();
  const {state,EVENTS,renderActivity,evValCell,evPctCell,openCompany,money,setWin,actWindow,actRows,actSorted,tapeKind}=P;
  const assert=(c,m)=>{if(!c){console.error("FAIL:",m);process.exit(1);}console.log("ok:",m);};
  const idxsrc=require("fs").readFileSync("index.html","utf8");

  assert(state.live.panel && state.live.events, "panel + events loaded live (history.csv not in zip: hist="+state.live.hist+")");
  assert(EVENTS.length>12000, "events loaded: "+EVENTS.length);

  // ---- the seal is the only gate ----
  renderActivity();
  assert(!idxsrc.includes('classList.toggle("gated",!state.pro)'),
    "no section gates its controls by tier");
  assert(!idxsrc.includes('id="tjgate"')&&!idxsrc.includes('id="trends"'),
    "the Trajectories section is gone");
  // THE FRONT DOOR (2026-09-23): the home page is the thesis, the search,
  // four stamped pills, the three biggest founder moves of the week, the
  // three largest stakes, the method, one ask. No table, no tape module:
  // /companies/ and /tape/ are one click away and the page competes with
  // neither.
  assert(idxsrc.indexOf('class="hero"')<idxsrc.indexOf('id="fweek"')&&idxsrc.indexOf('id="fweek"')<idxsrc.indexOf('id="stakes"')&&idxsrc.indexOf('id="stakes"')<idxsrc.indexOf('id="methodsec"')&&idxsrc.indexOf('id="methodsec"')<idxsrc.indexOf('id="homecap"')&&idxsrc.indexOf('id="homecap"')<idxsrc.indexOf('<footer>'),
    "sections run hero, the week, the stakes, the method, the ask, footer");
  assert(!idxsrc.includes('class="activitysec')&&!idxsrc.includes('id="actwrap"'),
    "the tape module left the home page for /tape/");
  assert(idxsrc.indexOf('<template id="pagesrc">')>-1&&idxsrc.indexOf('class="tablesec')>idxsrc.indexOf('<template id="pagesrc">')&&idxsrc.indexOf('id="tbody"')>idxsrc.indexOf('<template id="pagesrc">'),
    "the table markup survives only inside the inert extraction template");
  assert(idxsrc.includes('class="navsearch herosearch"')&&idxsrc.includes('id="hq"')&&idxsrc.includes(".home .topnav .navsearch{display:none}"),
    "the hero carries the big search (#hq, bound first by search.js); the nav's box hides on the home page and rides every other page");
  assert(idxsrc.includes('id="fwrows"')&&idxsrc.includes('id="stakecards"')&&idxsrc.includes('id="lednum"')&&idxsrc.includes('id="herostats"'),
    "every section is a stamp anchor: the page is real HTML before any script");
  assert(idxsrc.includes('<a class="exit" href="/tape/">The full tape &rarr;</a>')&&idxsrc.includes('<a class="exit" href="/companies/">All companies &rarr;</a>'),
    "both previews exit the same way: heading left, the full page right");
  assert(idxsrc.includes('id="homesub"')&&idxsrc.includes("/api/subscribe")&&idxsrc.includes("moves more than 1%")&&idxsrc.includes("Watch the founders"),
    "one ask: the day a founder's stake moves more than 1%");
  assert(idxsrc.includes('excluded, not guessed'),"the method strip carries the honesty line");
  assert(idxsrc.includes('if($("#tbody")){renderStatus();loadData();}'),
    "the stamped home page loads no CSVs: the machinery boots only where its anchors exist");
  assert(idxsrc.includes('<a href="/tape/">Activity</a>')&&idxsrc.includes('<a href="/companies/">Companies</a>')&&!idxsrc.includes('>Scoreboard<')&&!idxsrc.includes('>Performance<'),
    "the nav is Activity · Companies · Letter · Alerts · About");
  assert(!/class="blurred"/.test(els["#actwrap"]._html),"no blur class from the old gate anywhere: a sealed figure is a data-shape placeholder");

  // ---- THE TAPE: a weather line, the controls, one table grouped by kind ----
  // EVERY FILING BY THE CHIEF EXECUTIVE IS A ROW (2026-09-15), on the tape
  // and the company page alike; the kind chips are the company page's.
  {
    assert(!idxsrc.includes('id="actcards"')&&!idxsrc.includes('id="actsort"'),"no card grid, no sort chips: the table is the tape");
    setWin(365); state.ev.f=false; state.ev.kind="all"; state.ev.moved=false; renderActivity();
    const rows=actSorted(actRows());
    // THE HOME PAGE IS AN EXCERPT: ten rows, the full tape a click away
    assert((els["#actwrap"]._html.match(/class="dayrow/g)||[]).length===10&&/^10 of [\d,]+ filings/.test(els["#actnote"]._html),"ten rows, and the note says of how many: "+els["#actnote"]._html.slice(0,40));
    P.TAPE_LIMIT=0;
    assert(rows.length>50,"the window holds the year's filings: "+rows.length);
    assert(rows.some(e=>e.c==="A")&&rows.some(e=>e.c==="G")&&rows.some(e=>e.c==="F"),"awards, gifts and withholding are rows of the tape, not filtered before the kind is decided");
    assert(!rows.some(e=>e.pre),"a pre-IPO catch-up row stays on the company page");
    // THE LEDGER'S ORDER (2026-09-24): the filed day newest first; within a
    // day the move ranks the rows, unstated figures last; the kinds are the
    // filter chips now, not the sort
    const order={bought:0,disc:1,sold:2,plan:3,comp:4,xfer:5};
    const ks=rows.map(e=>order[tapeKind(e)]);
    const fds=rows.map(e=>(e.fd||"").slice(0,10));
    assert(fds.every((d,i)=>i===0||d<=fds[i-1]),"the filed day descends the tape");
    assert(ks.includes(0)&&ks.includes(1)&&ks.includes(3)&&ks.includes(4)&&ks.includes(5),"bought, discretionary, planned, compensation and transfer all present in a year");
    assert(!ks.includes(2),"no 'not stated' sale in the last year: every Form 4 since April 2023 carries the box");
    const mv=e=>{const p=P.evMove(e);return p?Math.abs(p.v):null;};
    for(const d of [...new Set(fds)]){const g=rows.filter(e=>(e.fd||"").slice(0,10)===d);
      const gm=g.map(mv);const ranked=gm.filter(x=>x!==null);
      assert(ranked.every((x,i)=>i===0||x<=ranked[i-1]),"ranked by the stake's move within the day "+d);
      const firstNull=gm.indexOf(null);if(firstNull>=0)assert(gm.slice(firstNull).every(x=>x===null),"unstated figures close their day "+d);}
    const html=els["#actwrap"]._html;
    renderActivity();
    assert(els["#actwrap"]._html.includes('class="tape"')&&(els["#actwrap"]._html.match(/class="dayrow/g)||[]).length===rows.length,"one table row per filing, once the excerpt's limit is lifted");
    assert(/data-key="kind">Kind<span class="arr">.*data-key="co">Company.*data-key="ceo">CEO.*data-key="v">Amount.*data-key="sh">Shares.*data-key="ch">Of holding.*data-key="st">Stake/.test(html)&&!html.includes('data-key="td"'),"seven sortable columns (2026-09-24): the date left for the day headers");
    assert(/class="detail tdt" title="[^"]*; filed /.test(html),"a trade from another day carries the manner, the lag and the filed day on its note's hover (2026-09-24)");
    // THE HEADERS SORT, LIKE THE SCOREBOARD'S; Kind restores the tape's own order
    P.setTapeSort("v"); {const r=actSorted(actRows()); const vs=r.map(e=>((e.c==="P"||e.c==="S")&&e.v&&!e.fl)?e.v:null).filter(x=>x!==null); assert(vs.every((x,i)=>i===0||x<=vs[i-1]),"Amount sorts descending on the first click"); assert(els["#actwrap"]._html.includes('data-key="v">Amount<span class="arr"> ↓'),"and the header shows the arrow");}
    P.setTapeSort("v"); {const r=actSorted(actRows()); const vs=r.map(e=>((e.c==="P"||e.c==="S")&&e.v&&!e.fl)?e.v:null).filter(x=>x!==null); assert(vs.every((x,i)=>i===0||x>=vs[i-1]),"a second click reverses");}
    P.setTapeSort("fd"); {const r=actSorted(actRows()); const ds=r.map(e=>e.fd); assert(ds.every((x,i)=>i===0||x<=ds[i-1]),"Filed sorts newest first");}
    P.setTapeSort("ceo"); {const r=actSorted(actRows()); const cs=r.map(e=>e.ceo||""); assert(cs.every((x,i)=>i===0||x.localeCompare(cs[i-1])>=0),"a name column sorts A to Z on the first click");}
    P.setTapeSort("kind"); assert(state.ev.sort.key===null,"Kind is the tape's own order again");
    // THE DAYS ARE THE STRUCTURE (2026-09-24): in the tape's own order the
    // rows sit under day headers, newest filed day first, each an anchor;
    // a column sort flattens the table and Kind brings the days back
    {const full=els["#actwrap"]._html;const days=[...new Set(actSorted(actRows()).map(e=>(e.fd||"").slice(0,10)))];
     assert((full.match(/class="dgrp"/g)||[]).length===days.length,"one day header per filed day");
     assert(full.includes(`id="d${days[0]}"`)&&full.indexOf('class="dgrp"')<full.indexOf('class="dayrow'),"the newest day heads the tape, before its rows");
     assert(full.includes(`href="#d${days[0]}"`),"the day header is an anchor");}
    P.setTapeSort("v"); assert(!els["#actwrap"]._html.includes('class="dgrp"'),"a column sort flattens the days away");
    P.setTapeSort("kind");
    assert(idxsrc.includes("; filed ${shortDay(e.fd)}"),"the filed day rides the trade note's hover");
    // THE SCOREBOARD IS AN OWNERSHIP TABLE (2026-09-17): the 12-month change in the stake and the as-of date, not the last trade
    assert(!idxsrc.includes('data-key="asof"')&&!idxsrc.includes('data-key="ltf"')&&!idxsrc.includes('data-key="c12"'),"the scoreboard is stake, worth, market cap, and no date or trade columns");
    assert(html.includes("openCompany(")&&html.includes("sec.gov"),"rows are doors and the amount links to the filing");
    assert(!html.includes("DISCRET."),"kinds are spelled out");
    {const full=els["#actwrap"]._html;assert(full.includes('class="kind comp"')&&/class="detail">(<a [^>]+>)?award granted/.test(full)&&full.includes('class="kind xfer"')&&/class="detail">(<a [^>]+>)?gift</.test(full),"a grant and a gift carry the badge and the filing's label in grey, the label linking to the filing");}
    // the amount is the Form 4's own number: on every purchase and sale, including the sale inside an exercise; a dash on a grant
    const exRow=rows.find(e=>e.lb==="exercise, part sold"&&e.v&&!e.mk&&e.u);
    if(exRow){const one=P.actRow(exRow);assert(one.includes(P.money(exRow.v))&&one.includes('class="kind comp"')&&one.includes("options cashed, part kept"),"the sale inside an exercise shows its value under the Compensation badge");}
    const awRow=rows.find(e=>e.c==="A"&&!e.mk);
    {const one=P.actRow(awRow);assert(one.includes("states no price for this row")&&!/\$[\d.]+[MK]/.test(one.slice(one.indexOf('class="n v"'),one.indexOf('class="n ch"'))),"a grant's amount is a dash that says why");}
    // dimming: a stated move under 1% is dimmed, whatever the kind; a grant that moved the stake is not
    const smallTrade=rows.find(e=>{const p=P.evMove(e);return p&&Math.abs(p.v)<1&&(tapeKind(e)==="plan"||tapeKind(e)==="disc");});
    const smallComp=rows.find(e=>{const p=P.evMove(e);return p&&Math.abs(p.v)<1&&e.c==="F";});
    const bigComp=rows.find(e=>{const p=P.evMove(e);return p&&Math.abs(p.v)>=5&&tapeKind(e)==="comp";});
    assert(smallTrade&&!P.evDim(smallTrade)&&smallComp&&P.evDim(smallComp)&&bigComp&&!P.evDim(bigComp),"a purchase or a sale never dims; a grant or a withholding under 1% does, one that moved the stake does not");
    assert(P.evDim({c:"S",lb:"exercise and sell",pl:"discretionary",pc:null,po:2}),"a sale the site says left the position unchanged is dimmed");
    const stats=els["#actstats"]._html;
    assert(/class="hstat"><div class="n">\d+<\/div><div class="k">bought on the open market<\/div>.*sold at their own discretion.*sold on a plan.*paid in shares.*gave shares away/.test(stats),"the week in five numbers, as stat blocks (2026-09-18): "+stats.replace(/<[^>]+>/g,""));
    assert(!/did not move a stake/.test(stats)&&!idxsrc.includes("did not move a stake"),"the tape never again says a filing did not move a stake unless its move was under 1%");
    // a plan is never counted as a cut; compensation never as a cut
    const cut=+(stats.match(/<div class="n">(\d+)<\/div><div class="k">sold at their own discretion/)||[])[1];
    const discPeople=new Set(actWindow().filter(e=>tapeKind(e)==="disc").map(e=>e.tk+"|"+e.ceo)).size;
    assert(cut===discPeople,"'cut a stake' counts discretionary sellers only: "+cut+" vs "+discPeople);
    const paid=+(stats.match(/<div class="n">(\d+)<\/div><div class="k">paid in shares/)||[])[1];
    const paidPeople=new Set(actWindow().filter(e=>tapeKind(e)==="comp"&&(e.c==="A"||e.c==="M"||e.lb==="exercise, part sold"||e.lb==="vested and sold")).map(e=>e.tk+"|"+e.ceo)).size;
    assert(paid===paidPeople&&paid>0,"'paid in shares' counts people who took shares as compensation, by kind, never by a sealed figure: "+paid);
    // the chips
    const chips=els["#actkinds"]._html;
    assert(/data-kind="all"[^>]*>All <small>\d+<\/small>/.test(chips)&&chips.includes('data-kind="comp"')&&chips.includes("Transfers <small>")&&chips.includes("Moved the stake &ge; 1%"),"the company page's chips, with counts: "+chips.replace(/<[^>]+>/g," ").slice(0,80));
    P.setKind("bought"); assert(actRows().every(e=>tapeKind(e)==="bought")&&actRows().length>0,"Bought shows purchases only");
    P.setKind("sold"); assert(actRows().every(e=>["disc","plan","sold"].includes(tapeKind(e))),"Sold is discretionary, planned and not stated together");
    P.setKind("comp"); assert(actRows().every(e=>tapeKind(e)==="comp")&&actRows().some(e=>e.c==="A"),"Compensation holds the awards");
    P.setKind("xfer"); assert(actRows().every(e=>tapeKind(e)==="xfer"),"Transfers holds the gifts");
    P.setKind("all"); P.setMoved(true); assert(actRows().every(P.evMoved)&&actRows().length<rows.length,"Moved the stake >= 1% keeps only stated moves of 1%+");
    P.setMoved(false);
    // the subhead names the window's dates
    assert(/^(Founder-led|Every CEO) · \d+ [A-Z][a-z]{2}–\d+ [A-Z][a-z]{2}$/.test(els["#tapesub"]._text||""),"the caption is who · when (2026-09-18): "+els["#tapesub"]._text);
    // every window is open; the notes carry no tier
    setWin(7); renderActivity();
    assert(state.ev.win==="7","the 7-day window sets");
    setWin(30); assert(state.ev.win==="30","a longer window opens");
    setWin(365);
  }

  // ---- the kinds, one row of each, decided by the shared function ----
  {
    const k=(c,lb,pl,pre)=>tapeKind({c,lb,pl:pl||"unknown",pre:!!pre});
    assert(k("P","open-market purchase","discretionary")==="bought"&&k("P","scheduled purchase","plan")==="bought","a purchase, open-market or scheduled");
    assert(k("S","discretionary sale","discretionary")==="disc"&&k("S","scheduled sale","plan")==="plan"&&k("S","sale","unknown")==="sold","the three sales");
    assert(k("S","exercise and sell","discretionary")==="comp"&&k("S","vested and sold","plan")==="comp"&&k("P","purchase, position unchanged","discretionary")==="comp","a sale that is compensation cashed is compensation, whatever the box says");
    assert(k("A","award granted")==="comp"&&k("M","options exercised")==="comp"&&k("F","shares withheld for tax")==="comp"&&k("D","forfeited")==="comp"&&k("X","other transaction")==="comp","the company's codes are compensation");
    assert(k("G","gift")==="xfer"&&k("C","converted")==="xfer"&&k("J","other transaction")==="xfer"&&k("W","other transaction")==="xfer","the rest are transfers");
    assert(k("P","open-market purchase","discretionary",true)==="xfer","a pre-IPO catch-up is a transfer on the company page and not on the tape");
    assert(P.tapeGroup({c:"S",lb:"sale",pl:"unknown"})==="sold"&&P.tapeGroup({c:"A",lb:"award granted"})==="comp","the group is the chip");
    assert(P.tapeDetail({c:"S",lb:"sale",pl:"unknown"})==="not stated"&&P.tapeDetail({c:"S",lb:"exercise, part sold",pl:"plan"})==="options cashed, part kept"&&P.tapeDetail({c:"F",lb:"shares withheld for tax"})==="withheld for tax","the detail is the filing's label in the site's words");
    assert(P.tapeManner({c:"S",lb:"sale",pl:"unknown"})==="Plan not stated"&&P.tapeManner({c:"S",lb:"scheduled sale",pl:"plan"})==="Pre-set plan","the manner on the hover");
    // THE GUARD: a filing with no purchase or sale that takes the position to zero is not ranked
    const zero={tk:"ZERO",ceo:"Gone Person",c:"D",lb:"forfeited",pl:"unknown",sh:1402911,v:null,fd:"2026-09-01",td:"2026-09-01",pc:-100,po:0,ha:0,nc:-1402911,rs:null,u:"https://www.sec.gov/z"};
    assert(P.evMove(zero)===null&&P.moveWhy(zero).includes("takes the position on record to zero"),"a forfeiture of the whole holding is not ranked, and the cell says why");
    assert(P.evMove({...zero,c:"S",lb:"discretionary sale",pl:"discretionary"})!==null,"a sale of the whole holding is a sale, and is ranked");
    const savedE=P.EVENTS;
    P.EVENTS=savedE.concat([zero,{tk:"OLDS",ceo:"Old Seller",c:"S",lb:"sale",pl:"unknown",sh:1000,v:2e6,fd:"2026-09-02",td:"2026-09-01",pc:-3,po:4,ha:1e6,nc:-1000,rs:null,u:"https://www.sec.gov/o"}]);
    state.ev.f=false; setWin(30); renderActivity();
    const h=els["#actwrap"]._html;
    const z=h.slice(h.indexOf("openCompany('ZERO')"),h.indexOf("openCompany('ZERO')")+1400);
    assert(z.includes('class="kind comp"')&&z.includes("forfeited")&&z.includes("takes the position on record to zero")&&!z.includes("sold out"),"the guarded row is on the tape, badged, its change unranked and explained");
    const o=h.slice(h.indexOf("openCompany('OLDS')"),h.indexOf("openCompany('OLDS')")+1400);
    assert(o.includes('class="kind sold"')&&o.includes('class="detail">not stated')&&o.includes("$2M"),"a pre-2023 sale reads Sold, not stated (the detail unlinked: the amount carries the link), with its amount");
    P.EVENTS=savedE; setWin(365); renderActivity();
  }


  // ---- the first-ever purchase ----
  {
    const savedE=P.EVENTS;
    P.EVENTS=[{tk:"NEWB",ceo:"First Timer",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:5e5,fd:"2026-09-03",td:"2026-09-02",pc:2.5,po:41.0,ha:41000,nc:1000,rs:null,u:"https://www.sec.gov/x",fb:true},
              {tk:"OLDB",ceo:"Old Hand",c:"P",lb:"open-market purchase",pl:"discretionary",sh:1000,v:9e5,fd:"2026-09-03",td:"2026-09-02",pc:0.1,po:1.0,ha:1e6,nc:1000,rs:null,u:"https://www.sec.gov/y",fb:false}];
    state.ev.f=false; setWin(30); renderActivity();
    assert(els["#actstats"]._html.includes('<div class="n">1</div><div class="k">first buy on record</div>'),"the stats count first-ever purchases");
    assert(els["#actwrap"]._html.includes('class="firstb"'),"and the row carries the tag");
    P.EVENTS=savedE; setWin(365); renderActivity();
  }



  // ---- the named screens: four questions, each a predicate the build also counts ----
  {
    const savedP=P.PANEL,savedC=P.SCREEN_COUNTS,savedL=P.state.screen;
    P.PANEL=[{tk:"NS",co:"Never",ceo:"a",pct:12,val:1,conf:"high",asof:"2026-09-01",fd:true},
             {tk:"HI",co:"Hired",ceo:"b",pct:0.3,val:1,conf:"high",asof:"2026-09-01",fd:false}];
    P.SCREEN_COUNTS={"s:over-10":3,"s:hired-under-1":2};
    P.TABLE_LIMIT=0;
    P.setScreen("over-10");
    const rowsOf=()=>[...els["#tbody"]._html.matchAll(/<tr onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
    let tks=rowsOf();
    assert(tks.length===1&&tks[0]==="NS","over-10 keeps the one who owns more than a tenth: "+JSON.stringify(tks));
    P.setScreen("hired-under-1");
    tks=rowsOf();
    assert(tks.length===1&&tks[0]==="HI","hired under 1% keeps the hired CEO with the small stake");
    assert(P.state.who==="hired"&&P.state.max===1&&P.state.min===0&&P.state.sold==="any","a screen is the whole question: its preset on, the other groups at the default");
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
    .map(([tk,co,ceo])=>({tk,co,ceo,pct:5,sh:1,out:1,val:1e9,conf:"high",pns:tk!=="DNX",lds:tk==="DNX"?day(6):"",ldb:tk==="UPX"?day(31):""}));
  const savedPanel=P.PANEL,savedEvents=P.EVENTS,savedF0=P.FOUNDERS;
  P.PANEL=fakePanel;P.FOUNDERS={UPX:{f:"yes",ev:"founded it",src:"x"}};
  P.EVENTS=[{tk:"DNX",ceo:"B Exec",c:"S",lb:"discretionary sale",pl:"discretionary",fd:day(5),td:day(6),sh:100,v:1e6,pc:1,ha:600,nc:-100,rs:0,u:"https://sec.gov/x"},
            {tk:"UPX",ceo:"A Founder",c:"P",lb:"open-market purchase",pl:"discretionary",fd:day(30),td:day(31),sh:30,v:3e5,pc:2,ha:150,nc:30,rs:0,u:"https://sec.gov/y"},
            {tk:"UPX",ceo:"A Founder",c:"S",lb:"exercise and sell",pl:"plan",fd:day(2),td:day(2),sh:5,v:1e4,pc:null,ha:150,nc:0,rs:0,u:""}];
  for(const r of P.PANEL){r.r1=r.tk==="UPX"?41.2:r.tk==="DNX"?-12.5:null;}   /* the 1-yr return rides on the row (universe.csv: ret_1y) */
  state.q="";Object.assign(state,P.DEFAULTS);state.sort={key:"r1",dir:-1};
  P.renderTable();
  let tb=els["#tbody"]._html;
  const order=[...tb.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(order[0]==="UPX"&&order[1]==="DNX"&&order[2]==="NOH","sorted by 1-yr return: the riser, the faller, then the one with no year of prices: "+order.join(",")+" r1="+P.PANEL.map(r=>r.r1).join(","));
  assert(/UPX[\s\S]*?c-r1">\+41\.2%/.test(tb),"the riser reads +41.2%, uncoloured (2026-09-18)");
  assert(/DNX[\s\S]*?c-r1">-12\.5%/.test(tb),"the faller reads -12.5%, uncoloured");
  assert(!tb.includes('class="tbar"')&&!tb.includes("c-conf"),"no bar in the ownership cell, no confidence column: every cell is one value");
  assert(!tb.includes("pts"),"nobody is told about points");
  assert(!tb.includes('class="spark"'),"no chart preview in the screener -- the number says it, the company page draws it");
  assert(tb.includes('class="n num c-mc"'),"a market cap column");
  const rowOf=tk=>{const i=tb.indexOf(`onclick="openCompany('${tk}')"`);const j=tb.indexOf("</tr>",i);return tb.slice(i,j);};
  // NEVER SOLD IS A SWITCH, NOT A COLUMN: a claim you ask for, not one made about everyone
  assert(!tb.includes('class="nsy"')&&!tb.includes("c-ns"),"no never-sold column in the table");
  {P.state.sold="none";P.renderTable();const on=els["#tbody"]._html;
   assert(on.includes("openCompany('UPX')")&&on.includes("openCompany('NOH')")&&!on.includes("openCompany('DNX')"),"the Never sold switch keeps the one who never reduced a stake and the short record, drops the seller -- options cashed don't count");
   P.state.sold="any";P.renderTable();}
  // the last move's kind still sorts and screens (r.ltk) but is no longer a column (2026-09-17): the table is ownership, the tape is trades
  assert(!rowOf("DNX").includes('class="c-lt"')&&!rowOf("DNX").includes('c-amt')&&!rowOf("DNX").includes('c-c12')&&!rowOf("DNX").includes('c-asof'),"the row carries the 12-month stake change, no trade cells, no date");
  assert(!tb.includes('class="c-asof"'),"no as-of column: a June filing must not read as a stale site (2026-09-17)");
  assert(!/c-lt"><span class="kind/.test(rowOf("DNX"))&&rowOf("UPX").includes('class="fb yes">FOUNDER')&&!rowOf("UPX").includes('c-fd'),"no last-move words in the table; the founder flag is the clay badge in the CEO cell (2026-09-24)");
  assert(!rowOf("NOH").includes(" pts"),"no 12-month column (2026-09-18): the table is stake, worth, market cap");
  state.sold="none";P.renderTable();
  const held=[...els["#tbody"]._html.matchAll(/onclick="openCompany\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(held.join(",")==="UPX,NOH","the Never sold switch keeps only those who never did: "+held.join(","));
  // the export: the rows as shown, every field, quoted where it must be
  const csv=P.exportTable();
  const hdr=csv.split("\n")[0];
  assert(hdr==="#,Company,Ticker,CEO,Founder,Ownership %,Value,Market cap,1-yr return %,Last move,Amount,Traded","the CSV is the table as shown, plus ticker and the founder flag as columns: "+hdr.slice(0,60));
  assert(csv.split("\n").length===3&&csv.includes("UPX")&&csv.includes("NOH")&&!csv.includes("DNX"),"and only the rows as filtered");
  assert(csv.split("\n")[1].split(",").length===hdr.split(",").length,"every row has every column");
  state.sold="any";state.sort={key:"r1",dir:1};P.renderTable();
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

  // ---- About, from first principles: what, where from, what ownership means, why ----
  {
    const about=require("fs").readFileSync("about.html","utf8");
    assert(about.includes("{{TOPNAV}}")&&about.includes("What ownership means here")&&about.includes("What a trade means here")&&about.includes("EDGAR"),
      "the About page says what the site is, where the numbers come from, what ownership and a trade mean");
    assert(!about.includes("PERF_SVG")&&!about.includes("confidence marks")&&!about.includes('class="dot high"'),"no chart, no marks legend: the site is about current ownership and how it moves");
  }

  // ---- founders-only, per section, independently ----
  {
    P.PANEL=[{tk:"TSLA",ceo:"Elon Musk",co:"Tesla",pct:29.9,val:9e11},
             {tk:"AAPL",ceo:"Tim Cook",co:"Apple",pct:0.02,val:1e9},
             {tk:"NVDA",ceo:"Jensen Huang",co:"NVIDIA",pct:3.5,val:1e11}];
    Object.assign(P.state,P.DEFAULTS,{who:"founders"});P.state.q="";P.renderTable();
    const shown=[...els["#tbody"]._html.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    const allF=shown.length&&shown.every(tk=>{const i=P.fInfo(tk);return i&&i.f==="yes";});
    assert(allF,"founders-only shows only proxy-named founders: "+shown.join(","));
    P.state.who="all";P.renderTable();
    const again=[...els["#tbody"]._html.matchAll(/openCompany\('([A-Z.]+)'\)/g)].map(m=>m[1]);
    assert(again.length>shown.length,"toggling off restores the full list");
    assert(P.state.ev.f===false&&P.state.sold==="any","the table's chips moved no other section's");
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
  // THE ABOUT PAGE, FROM FIRST PRINCIPLES (2026-09-14): what a reader must find there
  for(const t of ["What ownership means here",               // the definition, in words
                  "shares outstanding",                       // the denominator's source
                  "10-Q or 10-K",
                  "have not vested are not counted",          // what does not count
                  "proxy statement says so",                  // who is a founder
                  "Rule 10b5-1",                              // the kinds of trade
                  "EDGAR",                                    // where the numbers come from
                  "investment advice",
                  "corrections@founderledequities.com"])
    assert(about.includes(t),"about.html carries: "+t);

  // ---- one version, no tiers (2026-09-23) ----
  assert(!idx.includes("/api/me")&&!idx.includes("/pro/")&&!idx.includes("openPro")&&!idx.includes("state.pro"),
    "no session ask, no pro paths, no gate on the page");
  assert(idx.includes('["universe.csv","panel.csv"]')&&idx.includes('["events.csv"]')&&idx.includes('"history-lite.csv"'),
    "the data loads from one tree at the root");
  assert(!require("fs").existsSync("pro.html")&&!require("fs").existsSync("account.html")&&!require("fs").existsSync("functions/api/checkout.js")&&!require("fs").existsSync("functions/pro"),
    "the plan page, the account and the payment functions are gone from the code base");
  assert(idx.includes('id="navq"')&&idx.includes('src="/search.js"'),
    "the header carries the search box on every page (the topnav is shared)");
  assert(idx.includes('og:title')&&idx.includes('twitter:card')&&idx.includes('rel="canonical"'),
    "a pasted link unfurls as a card");
  {const head=idx.slice(0,idx.indexOf("</head>"));
   assert(head.includes('property="og:image" content="https://founderledequities.com/og.png"')&&head.includes('name="twitter:image"'),
     "a shared link unfurls with a picture");
   assert(require("fs").existsSync("ops/og_image.py")&&require("fs").readFileSync("ops/deploy.sh","utf8").includes("og_image.py"),
     "and the deploy draws it from tonight's numbers");
   assert(!/S&P 500 CEO ownership/.test(head)&&!/Every S&P 500 chief executive/.test(head),"the title and descriptions no longer describe an S&P-only site");
   assert(/2,000\+/.test(head)&&!/2,100\+/.test(head),"and say how many companies the site covers: 2,000+ since the partnership register (2026-09-16) took the site below 2,100");
   assert(!idx.includes('id="promodal"')&&!idx.includes('id="mcount"'),"the membership box is gone");
   assert(!about.includes("Until that page exists"),"About no longer promises a page that now exists");
   /* CEO wherever a reader scans; "chief executive" only inside About's prose */
   const visible=idx.replace(/<!--[\s\S]*?-->/g,"").replace(/\/\*[\s\S]*?\*\//g,"").replace(/^\s*\/\/.*$/gm,"");
   const labels=visible;
   assert(!/chief executive/i.test(labels),"no label on the page says chief executive: "+(labels.match(/.{0,40}chief executive.{0,40}/i)||[""])[0]);
   assert(idx.includes('<h1 id="thesis">What every CEO owns of the company they run.</h1>'),"the hero says what the site is, the same for every reader");
   assert(!idx.includes('See what moved')&&!idx.includes('Go Pro &middot; $15/mo</a>')&&!idx.includes("herobtns"),"no buttons on the fold: the sentence is the door, Pro is the header's");
   assert(!idx.includes('id="thisweek"'),"the fold is headline, method line, three numbers, the table: the week's sentence lives on /tape/ and in the letter");
   assert(!idx.includes('<a href="/pro/">Pro</a>')&&!idx.includes("Weekly tape, free")&&!idx.includes("navwatches"),"the header is where you are: Tape · Companies · Method and one button");
   assert(idx.includes("Filings through ")&&!idx.includes("Latest filing read"),"the dates are the footer's, not the hero's");
   assert(!idx.includes("Everything else is Pro."),"no pricing line on the fold: the one Pro hint on / is the scoreboard's count line");


   assert(idx.includes('"CEOs own more than 5%"')&&!idx.includes('"S&P 500 CEOs own more than 5%"'),"the rarity is one count over every company: no tiered denominator");
   assert(head.includes("what every CEO owns")&&idx.includes("CEOs own more than 5%")&&idx.includes('data-key="ceo">CEO<'),"the title, the strip and the screener say CEO");}
  assert(idx.includes('"/api/hit"')&&idx.includes("fle_nohit")&&idx.includes('hit("view","page")'),
    "the page counts its own visitors, and the owner can switch it off");
  assert(!idx.includes("document.cookie"),"and sets no cookie to do it");
  assert(idx.includes("Filings through")&&idx.includes("EVENTS.reduce"),
    "the footer dates the newest filing read, not the newest that moved a stake");
  const terms=require("fs").readFileSync("terms.html","utf8");
  for(const t of ["free to read","no account and no paid tier","one-click stop link","hello@founderledequities.com","not investment advice"])
    assert(terms.toLowerCase().includes(t.toLowerCase()),"terms.html carries: "+t);
  assert(!/Stripe|refund|trial|subscription/i.test(terms),"and sells nothing");

  // ---- the feed: a real year of the record, purchases and sales alike ----
  {
    const feedCsv=require("fs").readFileSync(require("fs").existsSync("site-data/events.csv")?"site-data/events.csv":"events.csv","utf8");
    const lines=feedCsv.trim().split("\n");
    const head=lines[0].split(",");
    const iCode=head.indexOf("code");
    let buys=0,sells=0;
    for(const l of lines.slice(1)){
      const c=l.split(",");
      if(c[iCode]==="P")buys++;
      else if(c[iCode]==="S")sells++;
    }
    assert(buys>500,"the feed carries the year's purchases: "+buys);
    assert(sells>100,"and its sales: "+sells);
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
  assert(els["#actstats"]._html.includes('<div class="n">1</div><div class="k">sold at their own discretion')&&els["#actstats"]._html.includes('<div class="n">1</div><div class="k">sold on a plan'),"the stats count the discretionary seller and the planned one apart");
  P.state.ev.f=true;renderActivity();
  const on=els["#actwrap"]._html;
  assert(on.includes("A Founder")&&!on.includes("A Hire"),"toggle on: founders only");
  assert((els["#tapesub"]._text||"").startsWith("Founder-led"),"and the caption says so");
  P.state.ev.f=true;P.EVENTS=savedE;P.FOUNDERS=savedF;setWin(365);renderActivity();
}

  console.log("\nALL RENDER PATHS PASS");
})().catch(e=>{console.error("HARNESS ERROR:",e);process.exit(1);});

