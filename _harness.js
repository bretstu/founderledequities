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
  const first=(...cands)=>{for(const c of cands)if(fs.existsSync(c))return c;return null;};
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
const runPage=new Function(js+"\n;return {get state(){return state},get EVENTS(){return EVENTS},set EVENTS(v){EVENTS=v},loadData,nFilings,evBadge,unchangedKind,pctOf,SEAL,renderActivity,evFiltered,evValCell,evPctCell,evTable,openDrawer,money,sortTape,renderFeed,sellKind,evBase,evSide,mannerOK,toggleKind,setKind,setView,setWin,evAgg,evColumn,renderCols,renderDay,dayShown,dayRows,dayText,gotoDay,filingDays,trajStats,soldTickers,sparkline,lastTrades,exportTable,chartBlock,cleanHist,renderBars,renderTable,fInfo,perfSeries,perfWindow,perfChart,renderPerf,perfReturns,perfBins,distChart,renderDist,distCrown,distPanel,get PERF(){return PERF},get HIST(){return HIST},set HIST(v){HIST=v},get PANEL(){return PANEL},set PANEL(v){PANEL=v},get FOUNDERS(){return FOUNDERS},set FOUNDERS(v){FOUNDERS=v},EVSAMPLE};");
const P=runPage();

(async()=>{
  await P.loadData();
  const {state,EVENTS,renderActivity,evFiltered,evValCell,evPctCell,evTable,openDrawer,money,sortTape,toggleKind,setView,setWin,evAgg,evColumn,renderCols,dayShown,dayRows,dayText,gotoDay,filingDays}=P;
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
  assert(idxsrc.indexOf('id="activity"')<idxsrc.indexOf('id="perfsec"')&&idxsrc.indexOf('id="perfsec"')<idxsrc.indexOf('id="table"'),
    "sections run leaderboard, activity, performance, table");
  assert(idxsrc.indexOf('href="#activity"')<idxsrc.indexOf('href="#perfsec"'),"and the nav follows the page");
  const freeCols=els["#actcols"]._html;
  assert(freeCols.includes("Bought")&&freeCols.includes("Sold"),"both columns render for a free reader");
  assert(!freeCols.includes("locked")&&!/class="blurred"/.test(freeCols),"no lock, no blur in the free view");
  assert(P.chartBlock("NVDA").includes("chartbox")||P.chartBlock("NVDA").includes("No trajectory"),
    "a free reader gets the real chart when the data is theirs");
  assert(els["#actday"]._html.includes("S&P 500"),"the free day strip names its scope: the S&P 500");
  // the harness maps /pro/universe.csv onto the root file, which may carry
  // sealed rows or none; the pro file never does, so it is unsealed by hand
  state.pro=true; const sealedPanel=P.PANEL; P.PANEL=sealedPanel.map(r=>({...r,masked:false})); renderActivity();
  assert(els["#actday"]._html.includes("companies")&&!els["#actday"]._html.includes("S&P 500"),
    "the pro day strip names the whole universe");
  // a pro session over a free-shaped file (sealed rows present) is still the S&P
  P.PANEL=sealedPanel.map(r=>({...r,masked:r.masked||r.tk==="ZZZ-SEALED"}));
  P.PANEL.push({tk:"ZZZ-SEALED",co:"Sealed",ceo:"x",pct:null,sh:null,masked:true});renderActivity();
  assert(els["#actday"]._html.includes("S&P 500"),"a pro reader over a sealed file is told the S&P, not a false universe");
  P.PANEL=sealedPanel; renderActivity();

  // ---- the day strip ----
  const newest=EVENTS.reduce((m,e)=>e.fd>m?e.fd:m,"");
  assert(dayShown()===newest,"the strip shows the newest filing day, not the calendar: "+newest);
  const rows=dayRows(newest);
  assert(rows.length>0&&rows.every(e=>e.fd===newest),"and every stake-moving trade on it: "+rows.length);
  assert(rows.every(e=>P.unchangedKind(e)===null),"the strip lists only trades that moved a stake");
  const allDay=dayRows(newest,true);
  assert(allDay.length>=rows.length&&allDay.every(e=>e.fd===newest),"the day's table holds every trade: "+allDay.length);
  const vals=rows.map(e=>(e.fl?0:e.v)||0);
  assert(vals.every((v,i)=>i===0||v<=vals[i-1]),"the day's rows run largest to smallest by value, buys and sales together");
  const kinds=allDay.map(e=>P.unchangedKind(e)===null?0:1);
  assert(kinds.every((k,i)=>i===0||k>=kinds[i-1]),"and the kept-apart trades stay beneath the line");
  if(allDay.length>rows.length){
    assert(els["#actday"]._html.includes("Also filed:")&&els["#actday"]._html.includes("kept apart"),
      "a day with unchanged-stake sales says so in one line beneath the strip");
    assert(P.dayText(newest,rows).includes("Also filed:"),"and the copy text carries the same line");
  }else assert(!els["#actday"]._html.includes("Also filed:"),"and a day without them has no such line");
  const dayHtml=els["#actday"]._html;
  assert(dayHtml.includes("Filed <b>")&&!dayHtml.includes("permalink")&&!dayHtml.includes("copy as text"),
    "the strip carries a readable date and no machinery");
  const chips=(dayHtml.match(/gotoDay\(/g)||[]).length;
  assert(chips===Math.min(5,filingDays().length),"one chip per filing day, the last five: "+chips);
  assert(/class="chip on"[^>]*>(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+\/\d+<i>/.test(dayHtml),"the newest day's chip is lit and reads like a day");
  assert((dayHtml.match(/class="dayrow"/g)||[]).length===rows.length&&dayHtml.includes('class="daylist"'),"one row per trade inside a fixed, scrolling frame");
  assert(dayHtml.includes("openDrawer(")&&dayHtml.includes("sec.gov"),"day rows are doors and carry filing links");
  assert(/class="dtd"[^>]*>traded (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+\/\d+</.test(dayHtml),"every strip row says when the trade happened");
  {const shown=dayHtml.replace(/title="[^"]*"/g,"");
   assert(!shown.includes("10b5"),"the rule's name lives in the definitions on hover, not in a label");
   assert(shown.includes("planned")||!rows.some(e=>e.pl==="plan"),"a planned trade is labelled planned");}
  const txt=dayText(newest,rows);
  assert(txt.split("\n").length===rows.length+2+(allDay.length>rows.length?1:0)&&txt.includes("?day="+newest),
    "the copy text is one line per trade, a headline, the also-filed line when there is one, and the permalink");
  assert(!txt.includes("null")&&!txt.includes("undefined"),"and prints no holes");
  const days=filingDays();
  gotoDay(days[days.length-2]);
  assert(dayShown()===days[days.length-2]&&(els["#actday"]._html.match(/class="chip on"/g)||[]).length===1,
    "choosing an earlier day lights that chip alone");
  gotoDay("");
  assert(dayShown()===newest,"and clearing the pin returns to it");
  // a day with no filings is an honest empty, not an error
  gotoDay("2019-01-01");
  assert(els["#actday"]._html.includes("No CEO")||dayRows("2019-01-01").length>0,
    "a day nobody filed says so");
  gotoDay("");

  // ---- the two columns: one bar per person ----
  assert(state.ev.win==="30","the window opens at 30 days");
  const B=evAgg("buys"),S=evAgg("sells");
  assert(B.pool.every(e=>e.c==="P"),"the buy column holds purchases only: "+B.pool.length);
  assert(S.pool.every(e=>e.c==="S"&&P.sellKind(e)!=="exsell"),"the sell column holds stake reductions only: "+S.pool.length);
  const keys=B.people.map(p=>p.tk+"|"+p.ceo);
  assert(new Set(keys).size===keys.length,"no chief executive twice in a column");
  assert(B.people.reduce((t,p)=>t+p.n,0)===B.pool.length,"every filing folds into exactly one person");
  for(let i=1;i<B.people.length;i++)assert(B.people[i-1].v>=B.people[i].v,"people rank by value, largest first");
  // THESE CHECKS RUN AGAINST THE REAL FEED, SO THEY ASSERT PROPERTIES,
  // NOT PARTICULAR PEOPLE. Every 10b5-1 seller files more than once a
  // year, so a twelve-month window always holds a repeat filer somewhere.
  setWin(365);
  const S365=evAgg("sells"),B365=evAgg("buys");
  const rep=[...B365.people,...S365.people].find(p=>p.n>=2);
  assert(rep&&rep.n>=2,"a repeat filer is one bar with a filing count: "+(rep&&rep.tk+" x"+rep.n));
  assert(evColumn(rep.n>=2&&B365.people.includes(rep)?"buys":"sells").includes(rep.n+" trades"),
    "and the bar says how many trades it folds");
  // rows are trades; a Form 4 covering two trade days is one filing
  const twoDay={};for(const e of P.evBase()){const k=e.acc;if(k)twoDay[k]=(twoDay[k]||0)+1;}
  const multi=Object.values(twoDay).some(n=>n>1);
  const strip=els["#actday"]._html;
  assert(/\d+ trades?( in \d+ filings?)? · /.test(strip),"the strip counts trades, and filings when they differ");
  if(multi)assert(P.nFilings(P.evBase())<P.evBase().length,"a two-day Form 4 counts as one filing, two trades");
  // the aggregate share of stake follows the pipeline's rule
  const one=[...B365.people,...S365.people].find(p=>p.n===1&&p.pc!==null);
  if(one){const side=B365.people.includes(one)?"buys":"sells";
    const e=P.evBase().find(e=>e.tk===one.tk&&P.evSide(e)===side);
    assert(Math.abs(one.pc-e.pc)<0.01,"a single filing's aggregate equals the feed's own percentage: "+one.tk);}
  // a person the pipeline declined a percentage for is declined here too,
  // with the same reason (Blackstone whenever Schwarzman bought this year)
  const und=[...B365.people,...S365.people].find(p=>p.pc===null);
  assert(!und||und.why.length>20,"an unstated share of stake carries its reason: "+(und&&und.tk));
  const bx=B365.people.find(p=>p.tk==="BX");
  if(bx)assert(bx.pc===null&&bx.why.includes("partnership units"),
    "Blackstone's aggregate declines a percentage and says why");
  else console.log("  (no Blackstone purchase in twelve months; partnership-units case not exercised)");
  assert(!S365.people.some(p=>p.v>1e11)&&!B365.people.some(p=>p.v>1e11),"a flagged price is worth nothing in a bar");
  // the exercise-and-sell rows are apart
  const exs=P.evBase().filter(e=>P.evSide(e)==="exsell");
  assert(exs.length>0&&!S365.pool.some(e=>e.lb in {"exercise and sell":1,"convert and sell":1,"sale, position unchanged":1}),
    "a sale that left the stake unchanged never enters the sell ranking, whatever its label");
  const sellHtml=evColumn("sells");
  assert(!sellHtml.includes("kept apart")&&!sellHtml.includes("Options cashed"),
    "the sell column carries no paragraph about unchanged-stake sales");
  renderCols();
  const note=els["#actnote"]._html;
  assert(exs.length?(note.includes("Kept out of everything above")&&note.includes("setView('exsell')")):note==="",
    "one sentence for the section says what was kept out and opens the table");
  assert(!note.includes("compensation"),"and never calls units compensation");
  const aboutTxt=require("fs").readFileSync("about.html","utf8");
  assert(aboutTxt.includes("does not move the stake is recorded")&&aboutTxt.includes("partnership units"),
    "the About page discloses the rule and its known limit");
  // a converted-and-sold row (Schwarzman-shaped) is apart, badged, and never called options
  const conv={tk:"BX",ceo:"S",c:"S",lb:"convert and sell",pl:"discretionary",sh:1,v:1,fd:"2026-01-01",td:"2026-01-01",pc:null,ha:0,nc:0,rs:null};
  assert(P.sellKind(conv)==="exsell"&&P.evSide(conv)==="exsell","a conversion-and-sale sits with the unchanged-stake sales");
  assert(P.evBadge(conv).t==="CONVERTED"&&!P.evBadge(conv).n.includes("compensation"),"and is badged as a conversion, not compensation");
  assert(P.evPctCell(conv).includes("unchanged"),"and states no percentage");
  assert(P.dayText("2026-01-01",[conv]).includes("converted and sold"),"and the copy text says converted");
  // a purchase the position did not register (Schwarzman's BX buys) is kept apart too
  const ghost={tk:"BX",ceo:"S",c:"P",lb:"purchase, position unchanged",pl:"discretionary",sh:1,v:1,fd:"2026-01-01",td:"2026-01-01",pc:null,ha:0,nc:0,rs:null};
  assert(P.evSide(ghost)==="exsell"&&P.unchangedKind(ghost)==="bought","a purchase the position did not register never enters the buy ranking");
  assert(P.evBadge(ghost).t==="UNCHANGED","and is badged unchanged, not bought");
  assert(P.evAgg("buys").pool.every(e=>e.lb!=="purchase, position unchanged"),"the buy column holds none of them");
  assert((sellHtml.match(/class="abar"/g)||[]).length<=8,"at most eight bars per column");
  assert(sellHtml.includes('class="seg plan"')||sellHtml.includes('class="seg disc"'),
    "a bar is segmented by manner");
  const mixed=S365.people.slice(0,8).find(p=>p.seg.disc>0&&p.seg.plan>0);
  if(mixed)assert(sellHtml.includes('class="seg disc"')&&sellHtml.includes('class="seg plan"'),
    "a person who sold both ways gets both segments: "+mixed.tk);
  assert(sellHtml.includes("Top 8 of")||S365.people.length<=8,"the footer counts the people beyond the top");
  // the founder mark: present exactly where the proxy says yes
  assert(!/repeating-linear-gradient/.test(idxsrc.slice(idxsrc.indexOf("recent activity ----------"))),
    "planned is the badge's light tint, not stripes -- one vocabulary for one fact");
  const fy=[...B365.people,...S365.people].find(p=>{const i=P.fInfo(p.tk);return i&&i.f==="yes";});
  const fn=[...B365.people,...S365.people].find(p=>{const i=P.fInfo(p.tk);return !i||i.f!=="yes";});
  const both=evColumn("buys")+evColumn("sells");
  const esc=x=>x.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
  if(fy)assert(new RegExp('<span class="nm">'+esc(fy.ceo)+'<\\/span><span class="fm"').test(both),"a founder gets the F pill after the name: "+fy.ceo);
  if(fn)assert(new RegExp('<span class="nm">'+esc(fn.ceo)+'<\\/span><\\/span>').test(both),"a hired chief executive does not: "+fn.ceo);
  assert(both.includes("F</span>founder")||!state.live.founders,"and the key explains the mark");
  assert(!both.includes("◆"),"the diamond is gone");
  setWin(30);

  // ---- manner chips are per column and independent ----
  const before=evAgg("sells").pool.length;
  toggleKind("sells","plan");
  assert(state.ev.kinds.sells.length===1&&state.ev.kinds.sells[0]==="disc","turning Planned off leaves Discretionary on the sell side");
  assert(evAgg("sells").pool.every(e=>e.pl==="discretionary"),"and the sell column is discretionary only");
  assert(state.ev.kinds.buys.length===2&&evAgg("buys").pool.length===B.pool.length,"the buy column did not move");
  toggleKind("sells","disc");
  assert(evAgg("sells").pool.length===0&&evColumn("sells").includes("Both manners are off"),
    "both chips off is an honest empty with the frame kept");
  toggleKind("sells","disc");toggleKind("sells","plan");
  assert(evAgg("sells").pool.length===before,"restoring both restores the column exactly");
  // inside 12 months every sale is classified, so both-on equals all
  setWin(365);
  const yr=P.evBase();
  assert(!yr.some(e=>e.c==="S"&&P.sellKind(e)==="unknown"),
    "inside twelve months every sale is classified — the checkbox exists after April 2023");
  const b365=evAgg("buys").pool.length;
  assert(b365>=B.pool.length,"a wider window holds at least as much");
  const w90=P.evBase().length;setWin(90);
  assert(P.evBase().length<=w90&&els["#actctl"]&&true,"the window chips narrow the pool");
  setWin(30);
  assert(evAgg("buys").pool.length===B.pool.length,"and 30 days returns to the opening view");

  // ---- the table opens on request, narrowed ----
  assert(state.ev.view===""&&!(els["#actwrap"]&&els["#actwrap"]._html.includes("escroll")),"the table starts closed — nothing rendered into it yet");
  setView("buys");
  assert(state.ev.view==="buys"&&evFiltered().every(e=>e.c==="P"),"opening from the buy column shows purchases: "+evFiltered().length);
  let proHtml=els["#actwrap"]._html;
  assert(proHtml.includes("escroll")&&proHtml.includes("efoot")&&proHtml.includes("purchase"),"the table renders with its footer");
  setView("sells");
  assert(evFiltered().every(e=>e.c==="S"&&P.sellKind(e)!=="exsell"),"the sell view is stake reductions");
  setView("exsell");
  assert(evFiltered().length>0&&evFiltered().every(e=>P.unchangedKind(e)!==null),
    "the stake-unchanged view is exactly those rows, whichever of the three labels they carry");
  setView("day");
  assert(evFiltered().every(e=>e.fd===newest),"the day view is the strip as a table");
  setView("");
  assert(state.ev.view==="","close closes");
  // a badge in a row opens the table on its own kind
  setView("sells");
  const badgeRow=evTable(evFiltered().slice(0,5),true);
  assert(/setKind\('(plan|disc|exsell|buys)'\)/.test(badgeRow),"a row badge filters to its own kind");
  P.setKind("plan");
  assert(state.ev.view==="sells"&&state.ev.kinds.sells.length===1&&state.ev.kinds.sells[0]==="plan"
    &&evFiltered().every(e=>e.pl==="plan"),"a Planned badge narrows the sell side to planned");
  state.ev.kinds.sells=["disc","plan"];
  // an empty result keeps the frame
  state.ev.q="zzzz-no-such-company";P.renderFeed();
  const emptyHtml=els["#actwrap"]._html;
  assert(emptyHtml.includes("escroll")&&emptyHtml.includes("eempty")&&emptyHtml.includes("<thead"),
    "the empty result keeps the table frame, message inside it");
  state.ev.q="";

  // the Nadella decimal-shift error must not top the value sort
  setWin(365);setView("sells");
  state.ev.sort={key:"v",dir:-1}; const top=evFiltered()[0];
  assert(!top.fl, "largest-value sort excludes flagged prices (top: "+top.tk+" "+money(top.v)+")");
  const msft=EVENTS.find(e=>e.tk==="MSFT"&&e.td==="2020-09-01"&&e.fl);
  assert(msft && msft.fl, "the $189bn filer error is flagged");
  assert(evValCell(msft).includes("⚠"), "and shown with a caution, as filed");
  // a residue too small to move the figure: stated with ≈, never silently
  const ap=EVENTS.find(e=>(e.pc===null||e.pc===undefined)&&e.pa!==null&&e.pa!==undefined);
  if(ap){assert(evPctCell(ap).includes("≈")&&evPctCell(ap).includes("unexplained"),"an approximate share of stake reads ≈ with the gap on hover: "+ap.tk);
    assert(P.pctOf(ap).approx===true,"and pctOf says it is approximate");}
  else console.log("  (no approximate-percentage rows in this feed; ≈ not exercised)");
  const strict=EVENTS.find(e=>e.pc!==null&&e.pc!==undefined&&e.c==="S"&&P.unchangedKind(e)===null);
  assert(!evPctCell(strict).includes("≈"),"a strict figure carries no ≈");
  const tko=EVENTS.find(e=>e.tk==="TKO"&&e.pc>100);
  assert(tko && evPctCell(tko).includes("≥100%"), "13,111% renders as ≥100%");
  const exs1=EVENTS.find(e=>e.lb==="exercise and sell");
  assert(evPctCell(exs1).includes("unchanged"), "exercise-and-sell shows stake unchanged");

  // search reaches by surname
  // search reaches by surname across every side of the window
  setWin(365);setView("");state.ev.sort={key:"fd",dir:-1}; state.ev.q="musk";
  const musk=P.evBase();
  assert(musk.length>0 && musk.some(e=>e.tk==="TSLA"), "search by surname reaches Musk (and, over the universe, whoever else matches): "+musk.length);
  state.ev.q="";setView("sells");

  // sorting is by column head
  P.sortTape("v"); assert(state.ev.sort.key==="v"&&state.ev.sort.dir===-1,"first click on a number head sorts descending");
  P.sortTape("v"); assert(state.ev.sort.dir===1,"second click flips it");
  P.sortTape("co"); assert(state.ev.sort.key==="co"&&state.ev.sort.dir===1,"a text head starts ascending");
  const alpha=evFiltered(); assert(alpha[0].tk<=alpha[alpha.length-1].tk,"company sort is alphabetical");
  P.sortTape("pc"); const bypc=evFiltered();
  assert(bypc[0].pc>=(bypc[Math.min(50,bypc.length-1)].pc||0),"share-of-stake sorts high to low");
  state.ev.sort={key:"fd",dir:-1};
  setWin(30);setView("");

  // money() must not print a thousand million
  assert(money(999959042)==="$1B","999,959,042 reads as $1B, not $1000M");
  assert(money(2.5e6)==="$2.5M"&&money(4.5e9)==="$4.5B","the ordinary cases still read right");

  // feed table markup for a real slice
  setView("sells");
  const t=evTable(evFiltered().slice(0,50),true);
  assert(t.includes("openDrawer(") && t.includes("sec.gov"), "rows are doors and carry filing links");
  assert(t.includes("sortTape('v')"), "the value head is clickable");
  setView("");

  assert((idxsrc.match(/^\/\*@shared\*\/$/gm)||[]).length>=25,"the declarations the company pages reuse are marked @shared");
  assert(idxsrc.includes('href="/company/${r.tk}/"'),"the drawer and the screener link to each company's page");
  assert((idxsrc.match(/class="pglink" href="\/company\/\$\{(e|p|r)\.tk\}\/"/g)||[]).length>=5,"every ticker on the page -- strip, trade table, bars, board -- is a door to its company's page");
  assert(idxsrc.includes('class="dco" href="/company/${r.tk}/"'),"the drawer's title is a door too");
  assert(idxsrc.includes('location.href=`/company/${tk}/`'),"Enter in the search box goes to the page");
  assert(typeof P.SEAL==="string"&&P.SEAL.length===1,"the seal glyph is defined (it was referenced in five places and defined in none)");
  // drawer with events present -- and the trade date leads there
  openDrawer("TSLA");
  assert(els["#drawer"]._html.includes("Latest trades"), "drawer prefers filed events");
  {const lag={tk:"SPCX",ceo:"Elon Musk",c:"S",lb:"discretionary sale",pl:"discretionary",fd:"2026-06-17",td:"2026-04-02",sh:11390,v:1.2e6,pc:0.002,ha:5e8,nc:-11390,rs:0,u:"https://sec.gov/z",pre:false,reg:"2026-05-20"};
   const row=evTable([lag],false);
   assert(/class="adate"[^>]*>2026-06-17<span class="atd">traded 2026-04-02/.test(row),"the trade table leads with the filing date and shows the trade date beneath when it differs");
   assert(row.includes("filed 76 days after the trade"),"and names a lag past two business days");
   const before=P.PANEL;P.PANEL=[{tk:"SPCX",co:"SpaceX",ceo:"Elon Musk",pct:33.76,sh:4.45e9,out:1.3e10,val:6e11,conf:"medium"}];
   const savedE=P.EVENTS;P.EVENTS=[lag];P.HIST={SPCX:[["2025-07-01",36.2,4.7e9],["2026-06-11",33.76,4.45e9]]};
   P.state.sort={key:"pct",dir:-1};P.state.q="";P.state.min=0;P.state.tbH=false;P.renderTable();
   const cell=els["#tbody"]._html;
   assert(/class="ltd">2026-04-02</.test(cell)&&cell.includes("filed 2026-06-17"),"the screener's last trade leads with the trade date, filing date on hover");
   openDrawer("SPCX");
   assert(/class="adate"[^>]*>2026-04-02</.test(els["#drawer"]._html),"the drawer's latest trades lead with the trade date");
   assert(P.dayText("2026-06-17",[lag]).includes("(traded 2026-04-02)"),"the copy text names the trade date when it is not the filing day");
   // and as the pipeline now labels it -- a pre-registration trade -- it is kept apart everywhere
   const pre={...lag,pre:true};
   assert(P.unchangedKind(pre)==="pre"&&P.evSide(pre)==="exsell","a pre-registration trade sits with the kept-apart pile");
   assert(P.evBadge(pre).t==="PRE-IPO"&&P.evBadge(pre).n.includes("2026-05-20"),"badged PRE-IPO with the registration date");
   assert(P.evPctCell(pre).includes("pre-IPO"),"no percentage against the public-company stake");
   P.EVENTS=[pre];P.renderTable();
   const trow=els["#tbody"]._html;
   assert(trow.includes("no trade that moved the public-company stake")&&trow.includes('class="nsy"'),"the screener shows no last trade and a never-sold check for a company whose only sale predates registration");
   assert(!P.soldTickers().has("SPCX"),"and it is not a seller");
   assert(P.dayText("2026-06-17",[pre]).includes("sold (pre-IPO)"),"the copy text says pre-IPO");
   P.PANEL=before;P.EVENTS=savedE;}

  // ---- the screener: three-year change, last trade, never sold ----
  const day=n=>new Date(Date.now()-n*86400e3).toISOString().slice(0,10);
  P.HIST={
    UPX:[[day(1400),5.0,100],[day(700),6.2,120],[day(30),9.1,150]],
    DNX:[[day(1400),12.0,900],[day(700),10.0,800],[day(5),7.5,600]],
    NOH:[[day(10),3.0,10]],
  };
  const fakePanel=[["UPX","Upward Inc","A Founder"],["DNX","Downward Inc","B Exec"],["NOH","Newlisted Inc","C Exec"]]
    .map(([tk,co,ceo])=>({tk,co,ceo,pct:5,sh:1,out:1,val:1e9,conf:"high"}));
  const savedPanel=P.PANEL,savedEvents=P.EVENTS;
  P.PANEL=fakePanel;
  P.EVENTS=[{tk:"DNX",ceo:"B Exec",c:"S",lb:"discretionary sale",pl:"discretionary",fd:day(5),td:day(6),sh:100,v:1e6,pc:1,ha:600,nc:-100,rs:0,u:"https://sec.gov/x"},
            {tk:"UPX",ceo:"A Founder",c:"P",lb:"open-market purchase",pl:"discretionary",fd:day(30),td:day(31),sh:30,v:3e5,pc:2,ha:150,nc:30,rs:0,u:"https://sec.gov/y"},
            {tk:"UPX",ceo:"A Founder",c:"S",lb:"exercise and sell",pl:"plan",fd:day(2),td:day(2),sh:5,v:1e4,pc:null,ha:150,nc:0,rs:0,u:""}];
  state.q="";state.min=0;state.tbF=false;state.tbH=false;state.sort={key:"d3",dir:-1};
  P.renderTable();
  let tb=els["#tbody"]._html;
  const order=[...tb.matchAll(/onclick="openDrawer\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(order[0]==="UPX"&&order[1]==="DNX"&&order[2]==="NOH","sorted by three-year change: the riser, the faller, then the record too short to say: "+order.join(",")+" d3="+P.PANEL.map(r=>r.d3).join(","));
  assert(/UPX[\s\S]*?class="d3 up"[\s\S]*?<b>\+4\.1%<\/b>/.test(tb),"the riser reads +4.1% in green, from the point on or before the horizon");
  assert(tb.includes("ownership 5.00% on")&&tb.includes("→ 5.00% now"),"and the hover spells out then and now");
  assert(/DNX[\s\S]*?class="d3 down"[\s\S]*?<b>−4\.5%<\/b>/.test(tb),"the faller reads −4.5% in red");
  assert(!tb.includes("pts"),"nobody is told about points");
  assert(!tb.includes('class="spark"'),"no chart preview in the screener -- the number says it, the drawer draws it");
  assert(tb.includes('class="n num c-mc"'),"a market cap column");
  const rowOf=tk=>{const i=tb.indexOf(`onclick="openDrawer('${tk}')"`);const j=tb.indexOf("</tr>",i);return tb.slice(i,j);};
  assert(rowOf("UPX").includes('class="nsy"')&&!rowOf("DNX").includes('class="nsy"'),"never sold is a check in its own column for the one who never reduced a stake — options cashed don't count");
  assert(rowOf("NOH").includes('class="nsy"'),"a short record with no sale on file is never-sold too");
  assert(rowOf("DNX").includes('class="ltv"')&&rowOf("DNX").includes("$1M"),"the last trade shows its value beside the badge");
  assert(!tb.includes('class="asof'),"as-of left the table for the drawer and the export");
  assert(rowOf("DNX").includes('class="abadge down"')&&rowOf("DNX").includes("SOLD")&&rowOf("UPX").includes("BOUGHT"),"the last trade that moved the stake, badged");
  assert(rowOf("NOH").includes("no trade that moved the public-company stake"),"and an honest dash where there is none");
  state.tbH=true;P.renderTable();
  const held=[...els["#tbody"]._html.matchAll(/onclick="openDrawer\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(held.join(",")==="UPX,NOH","the Never sold switch keeps only those who never did: "+held.join(","));
  // the export: the rows as shown, every field, quoted where it must be
  const csv=P.exportTable();
  const hdr=csv.split("\n")[0];
  assert(hdr.startsWith("ticker,company,chief_executive,founder,ownership_pct,shares_held,shares_outstanding,close,stake_value,market_cap,change_3y_pts"),"the CSV carries the fields the page does not show: "+hdr.slice(0,60));
  assert(csv.split("\n").length===3&&csv.includes("UPX")&&csv.includes("NOH")&&!csv.includes("DNX"),"and only the rows as filtered");
  assert(csv.split("\n")[1].split(",").length===hdr.split(",").length,"every row has every column");
  state.tbH=false;state.sort={key:"d3",dir:1};P.renderTable();
  const asc=[...els["#tbody"]._html.matchAll(/onclick="openDrawer\('([A-Z]+)'\)"/g)].map(m=>m[1]);
  assert(asc[0]==="DNX"&&asc[2]==="NOH","ascending puts the faller first and the short record still last");
  state.sort={key:"pct",dir:-1};
  P.PANEL=savedPanel;P.EVENTS=savedEvents;
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
     assert(!dist.items.some(i=>i.tk==="LATE")&&dist.skipped===1,"the late entrant has no close at the window's start and is counted as listed too recently, not placed");
     const {svg,bins,tint}=P.distChart(dist,P.perfBins("12"));
     assert((svg.match(/rx="2" fill="rgba/g)||[]).length===dist.items.length,"one tile per company (hit areas and axis boxes are not tiles)");
     {const crownedN=bins.reduce((n,b)=>n+Math.min(3,b.items.length),0);
      assert((svg.match(/<a href="\/company\//g)||[]).length===crownedN,"only a named tile is a link; a block is part of the column");}
     assert(svg.includes("S&amp;P 500 +10%"),"the benchmark is marked where it lands");
     assert(svg.includes(">below<")&&svg.includes(">above<")&&svg.includes(">-40% to<")&&svg.includes(">0% to<")&&svg.includes(">+40%<"),"a labelled box under every column says its range");
     {const boxes=(svg.match(/<rect x="[^"]+" y="[^"]+" width="[^"]+" height="34" rx="3" fill="(rgba[^"]+)"/g)||[]);
      assert(boxes.length===P.perfBins("12").length+1,"one box per column");
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
      assert(panel.includes("120 companies")&&panel.includes("Open these in the screener"),"with the count and a way to the screener");
      const order=[...panel.matchAll(/<b>(T\d+)<\/b>/g)].map(m=>m[1]);
      assert(order[0]==="T0"&&order[119]==="T119","sorted by return, lowest first");
      // a bin that ends at zero is a loss: red, not green
      const z=P.perfBins("12").indexOf(0);
      const tints=[...svg.matchAll(/height="34" rx="3" fill="(rgba\((\d+)[^)]*\))"/g)].map(m=>m[2]);
      assert(tints[z]==="194"&&tints[z+1]==="11","the -10% to 0% box is red and the 0% to +10% box is green");}
     els["#perfdist"]=els["#perfdist"]||el("#perfdist");
     P.renderDist(d);
     assert(els["#perfdist"]._html.includes("beat the S&amp;P 500"),"the caption says how many beat the benchmark");
     // the bins scale with the window
     assert(P.perfBins("12").length===9&&P.perfBins("60")[0]===-75&&P.perfBins("60").slice(-1)[0]===500,"a year moves in tens, five years in hundreds");
     // the screener follows: a Return column and the index chip
     const savedPanel2=P.PANEL;
     /* FE is FirstEnergy, a real S&P company: never inject a row the panel already has */
     P.PANEL=[...savedPanel2,...dist.items.filter(i=>!savedPanel2.some(p=>p.tk===i.tk)).map(i=>({tk:i.tk,co:"Co "+i.tk,ceo:"A Founder",pct:5,sh:1,out:1,val:1e9,conf:"high"}))];
     P.state._perfWin=d;P.state.tbI=true;P.state.q="";P.state.min=0;P.state.tbF=false;P.state.tbH=false;P.state.sort={key:"ret",dir:-1};
     P.renderTable();
     const tb=els["#tbody"]._html;
     assert(/c-ret"><span class="d3 (up|down|flat)"[^>]*><b>[+−]\d+%<\/b>/.test(tb),"a Return column with a signed figure");
     const shown=[...tb.matchAll(/onclick="openDrawer\('([A-Z0-9.-]+)'\)"/g)].map(m=>m[1]);
     const uniq=new Set(shown);
     assert(uniq.size===dist.items.length&&shown.every(tk=>dist.items.some(i=>i.tk===tk)),"the Founders index chip keeps only constituents: "+[...uniq].join(","));
     P.state.tbI=false;P.renderTable();
     assert(els["#tbody"]._html.includes("not in the Founders index"),"a company outside the index shows a dash in the column");
     // a bin click is a real filter: the bucket, by name, with a chip to clear it
     els["#rangechip"]=els["#rangechip"]||el("#rangechip");
     P.state.tbI=true;P.state.tbRange={lo:40,hi:null};P.renderTable();
     const inb=[...els["#tbody"]._html.matchAll(/onclick="openDrawer\('([A-Z0-9.-]+)'\)"/g)].map(m=>m[1]);
     assert(inb.length>0&&inb.every(tk=>{const it=dist.items.find(i=>i.tk===tk);return it&&it.ret>=40;}),"the range keeps only the bucket's companies: "+inb.join(","));
     assert(els["#rangechip"]._html.includes("Return above +40%"),"and the chip names the bucket");
     P.state.tbRange={lo:0,hi:10};P.renderTable();
     assert(!/onclick="openDrawer/.test(els["#tbody"]._html),"an empty bucket shows no rows");
     P.state.tbRange=null;P.state.tbI=false;
     P.PANEL=savedPanel2;P.state.sort={key:"pct",dir:-1};}
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
     assert(els["#perfnote"]._html.includes("dividends excluded")&&els["#perfnote"]._html.includes("equal weight (RSP)"),"the footnote states the method precisely and names both benchmarks");
     assert(els["#perfsub"]._html.includes("all ")||els["#perfsub"].textContent.includes("all "),"the subtitle names the cohort");
     P.state.pc="sp";P.renderPerf();
     assert((els["#perfsub"].textContent||els["#perfsub"]._html).includes("in the S&P 500"),"and says S&P 500 when that is the cohort");
     P.state.pc="all";P.PANEL=savedPanel3;P.renderPerf();}
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
   const labels=visible.replace(/of \$\{open\.toLocaleString\(\)\} chief executives own/g,"").replace(/of 500 chief executives own/g,"");
   assert(!/chief executive/i.test(labels),"no label on the page says chief executive: "+(labels.match(/.{0,40}chief executive.{0,40}/i)||[""])[0]);
   assert(idx.includes("${open.toLocaleString()} chief executives own"),"the hero is a sentence: the word, and the count with its comma");
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

  console.log("\nALL RENDER PATHS PASS");
})().catch(e=>{console.error("HARNESS ERROR:",e);process.exit(1);});
