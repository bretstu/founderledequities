/* the data's version, stamped by deploy.sh: every data fetch carries it so a
   deploy's files are cached until the next deploy changes the key */
const DATA_V="dev";
const withV=p=>p+(p.includes("?")?"&":"?")+"v="+DATA_V;
/* ---------------- the company page ----------------
   Everything above this line was extracted from index.html at deploy (the
   declarations marked @shared). Below: what this page does with it. */
const C=window.COMPANY||{};
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
let VIEW="all",BIG=false,TRADES_ALL=false,HELD_ALL=false;   /* BIG: only rows that moved the stake by 1% or more; TRADES_ALL: the record past its first 25 rows */


function setRow(row){
  PANEL=[row];
  if(C.founder)FOUNDERS[row.tk]=C.founder;
}

/* whose stake: "Elon Musk's", "Jabbok Schlacks'" */
const poss=n=>n+(/s$/i.test(n)?"'":"'s");


/* ---- the answer band: five cards ----
   THE LABELS ARE THE TABLE'S. Value, Market cap, 1Y return: the words the
   home page uses for the same numbers, computed the same way (shares x
   close; outstanding x close; the store's twelve-month price return).
   Nothing here is explained in a sentence; a figure that needed one has
   been taken off the page. The stake's own trajectory is the Stake
   chart's job, not a "3-year change" card that had to say "since 2026-01"
   when the record was eight months old. */
function stat(k,v,cls,sub,title){return `<div class="cstat"${title?` title="${esc(title)}"`:""}><div class="k">${k}</div><div class="v ${cls||""}">${v}</div>${sub?`<div class="s">${sub}</div>`:""}</div>`;}
function daysSince(d){
  if(!d)return null;
  const then=Date.parse(d+"T00:00:00Z");
  if(isNaN(then))return null;
  return Math.max(0,Math.floor((Date.now()-then)/86400000));
}
function band(r){
  const mcap=r.price&&r.out?r.out*r.price:null;
  /* THE KICKER SAYS WHAT ITS NUMBERS ARE (design v4): the ticker and the
     market cap named as such, one small mono line under the sentence. The
     founder flag lives in the hero's clay pill, baked by the build. */
  const kick=$("#ctk");
  if(kick){const fi=fInfo(r.tk);const b=fi&&fi.f==="yes"?` · <span class="kbadge">Founder-led</span>`:"";kick.innerHTML=`${esc(r.tk)}${mcap?` · ${money(mcap)} market cap`:""}${b}`;}
  /* THREE CARDS, LABEL FIRST (2026-09-23). The share, the shares and the
     worth live in the H1 and the first sentence; the cards say what the
     sentence does not. The label names the card, the figure answers it,
     the date is the fine print, and every card exists for every company:
     STAKE RANK by dollar value, LAST SALE, LAST BUY -- "None" with the
     record's first year when there has never been one. */
  const clock=(hit,word,withVal)=>{
    if(!hit||!hit.d)return ["None",`no ${word} since ${C.since||"2016"}`];
    const n=daysSince(hit.d);
    const v=n===null?esc(hit.d):`${fmt(n)}<small> days ago</small>`;
    return [v,`${dayLabel(hit.d)}${withVal&&hit.v?` · ${money(hit.v)}`:""}`];
  };
  /* the sale's fine print is its date; the buy carries its size too (design v4) */
  const [sv,ss]=clock(C.ls,"sales",false),[bv,bs]=clock(C.lb,"purchases",true);
  /* THE STAKE LEADS THE CARDS (2026-09-24): the home page teaches that the
     stake is a big clay number in a white card; the company page now keeps
     that promise. The H1 still says the sentence; the card is where a
     scanning eye finds the figure. */
  const wsub=r.pct!=null?(r.price&&r.sh?`worth ${money(r.sh*r.price)} at the latest close`:"of the common shares"):"see the note below";
  const cards=`<div class="cband kpi">
    ${stat("The stake",r.pct!=null?r.pct.toFixed(2)+"%":"&mdash;","clay",wsub,"shares held over shares outstanding, from the newest filing")}
    ${stat("Stake rank",C.rank?"#"+fmt(C.rank):"&mdash;","","by dollar value of the stake","every company on the site, ordered by what the chief executive's stake is worth at the latest close")}
    ${stat("Last sale",sv,"",ss,"the newest sale that moved the stake; exercises and same-day sell-offs that left it unchanged are not counted")}
    ${stat("Last buy",bv,"",bs,"the newest purchase that moved the stake")}
  </div>`;
  /* THE FLAGS KEEP THEIR LINE (2026-09-23): the answer card that carried
     them is gone, so a low-confidence stake, a partnership, or a stake
     the record could not measure says so right under the cards. */
  const flag=r.units?`Exchangeable partnership units rather than common stock, so a percent of common shares cannot describe the stake.`
    :r.pct===null?(r.flags||"the record could not settle on a figure")
    :r.conf==="low"?("the site's confidence in this stake is low: "+((r.flags||"").split("\n")[0]||"the record could not settle on a figure")):"";
  const flagLine=flag?`<div class="cnot"><span class="k">Caution</span> ${esc(flag)}</div>`:"";
  /* UNITS REPORTED AS SHARES (2026-09-29): where the walk found restricted
     stock units filed as common stock, the number includes them from the
     grant, and this line says so. Nothing where it did not. */
  const unitsLine=/restricted stock units this filer reports as shares/.test((C.row&&C.row.cautions)||"")?`<div class="cnot"><span class="k">Includes</span> restricted stock units this filer reports as shares before they vest.</div>`:"";
  /* NOT COUNTED (2026-09-19; folded to one line 2026-09-24): the lines the
     register removes, behind a one-line expander -- the fact that shares
     were left out stays beside the number it qualifies, the itemised
     footnote text is one click away instead of three lines on the page. */
  const excl=(C.row&&C.row.excluded_detail)||"";
  const items=excl?excl.split(" | ").filter(Boolean):[];
  const exclSh=num(C.row&&C.row.excluded_shares)||0;
  const notCounted=items.length?`<details class="cnot"><summary><span class="k">Not counted</span>${exclSh?fmt(exclSh)+" shares in ":""}${items.length} holding${items.length===1?"":"s"} the filings' own footnotes leave out</summary><div class="cnx">${items.map(x=>esc(x)).join("<br>")}</div></details>`:"";
  const heldHere=(C.held||[]).length>0;   /* the expander's home follows the section (2026-09-25) */
  if(heldHere)window.__notCounted=notCounted;
  return cards+flagLine+unitsLine+(heldHere?"":notCounted);
}

/* ---- the record: the price and the stake, with the trades on the line ----
   ONE POINT PER MONTH-END for the stake. The record steps at every filing
   and every cover-page count; at a ten-year scale that is a staircase of
   same-week moves that means nothing and looks like noise. Each month keeps
   its last point, and remembers why the month moved: a trade, a grant, a
   gift, tax withholding, options exercised, or the share count changing
   with no change in the holding. Trades keep their exact dates as dots.

   THE PRICE CHART answers the question a reader actually has about an
   insider: did they sell into a top, did they buy the crash. Daily closes,
   split-adjusted, from the price store; every dot sits at the price ON THE
   FILING, restated in today's shares, so the gap between a dot and the
   line is itself information. Grants, gifts and withholding are not
   decisions about price and are not drawn.

   The line draws in once on load. Hover is a crosshair with the day and
   the nearest trade, not the browser's grey tooltip. */
let PRICES_DAILY=null;   /* [[date, close], ...] for this ticker, or null */
const CODE_WORDS={P:"bought",S:"sold",A:"granted",G:"gift",F:"tax withholding",M:"options exercised",C:"converted",D:"returned to the company",J:"other",X:"options exercised"};
function monthEnds(pts){
  const out=[];let cur=null;
  for(const p of pts){
    const m=p[0].slice(0,7);
    if(!cur||cur.m!==m){if(cur)out.push(cur);cur={m,pt:p,codes:new Set()};}
    else cur.pt=p;
    for(const c of (p[3]||""))if(CODE_WORDS[c])cur.codes.add(c);
  }
  if(cur)out.push(cur);
  const series=[];
  for(let i=0;i<out.length;i++){
    const o=out[i],prev=series[i-1];
    const dS=prev?o.pt[2]-prev.sh:0,dP=prev?o.pt[1]-prev.pct:0;
    const why=[];
    for(const c of o.codes)why.push(CODE_WORDS[c]);
    if(prev&&Math.abs(dS)<1&&Math.abs(dP)>1e-6)why.push("share count changed");
    if(prev&&Math.abs(dS)>=1&&!o.codes.size)why.push(dS>0?"shares added":"shares removed");
    series.push({d:o.pt[0],m:o.m,pct:o.pt[1],sh:o.pt[2],why:why.join(", "),dP,dS});
  }
  return series;
}
function monthLabel(m){const [y,mo]=m.split("-");return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mo-1]+" "+y;}
function dayLabel(d){return monthLabel(d.slice(0,7)).replace(" ",` ${+d.slice(8,10)}, `);}
const dollars=v=>Math.abs(v-Math.round(v))<1e-9&&v>=1?"$"+Math.round(v).toLocaleString("en-US"):v>=1000?"$"+Math.round(v).toLocaleString("en-US"):v>=100?"$"+v.toFixed(0):v>=10?"$"+v.toFixed(1):"$"+v.toFixed(2);
/* the frame: narrow screens get a taller box so the line has room */
function frame(){const narrow=(window.innerWidth||1000)<600;return narrow?{w:520,h:340,pad:{l:54,r:16,t:26,b:30}}:{w:940,h:320,pad:{l:64,r:22,t:26,b:30}};}
const SELL="var(--sell)";
/* the dots, shared by both charts: sized by value, a white rim so
   neighbours stay distinct. Hover says what the trade was; the list
   below the chart carries the filing link. */
function dots(evs,X,Y,at,fr){
  const drawn=evs.slice().sort((a,b)=>(b.v||0)-(a.v||0));
  const vmax=Math.max(1,...drawn.map(e=>e.v||0));
  let out="";
  drawn.forEach((e,i)=>{
    const dt=e.td||e.fd;const [y,note]=at(e);const x=X(dt),yy=Y(y);
    const rr=3+5*Math.sqrt((e.v||0)/vmax);const buy=e.c==="P";const col=buy?"var(--buy)":SELL;
    out+=`<circle class="dot" style="--i:${Math.min(i,40)}" cx="${x.toFixed(1)}" cy="${yy.toFixed(1)}" r="${rr.toFixed(1)}" fill="${col}" fill-opacity="0.85" stroke="#fff" stroke-width="1.2"><title>${buy?"Bought":"Sold"} ${e.v?money(e.v):compact(e.sh)+" sh"} · ${compact(e.sh)} sh${note} · ${dt}${e.pl==="plan"?" · planned":e.pl==="discretionary"?" · discretionary":""}</title></circle>`;
  });
  return out;
}
function yearsAxis(X,t0,t1,fr){
  let out="";const y0=new Date(t0).getUTCFullYear(),y1=new Date(t1).getUTCFullYear();
  const every=(y1-y0)>7&&fr.w<600?2:1;
  for(let yr=y0+1;yr<=y1;yr++){if((yr-y0)%every)continue;const x=X(`${yr}-01-01`);if(x<fr.pad.l||x>fr.w-fr.pad.r)continue;
    out+=`<text x="${x.toFixed(1)}" y="${fr.h-10}" text-anchor="middle" font-family="var(--ui)" font-size="10.5" font-weight="500" fill="var(--faint)">${yr}</text>`;}
  return out;
}
/* the hover's data rides on the svg: one row per x-position the cursor can
   land on, [date, label lines...], plus the frame it was drawn in */
function hoverAttrs(rows,fr,t0,t1){
  return `data-t0="${t0}" data-t1="${t1}" data-l="${fr.pad.l}" data-r="${fr.pad.r}" data-w="${fr.w}" data-t="${fr.pad.t}" data-b="${fr.pad.b}" data-h="${fr.h}" data-rows="${esc(JSON.stringify(rows))}"`;
}
function priceChart(px,evs){
  const fr=frame(),{w,h,pad}=fr;
  if(!px||px.length<2)return "";
  const t0=Date.parse(px[0][0]),t1=Date.parse(px[px.length-1][0])||t0+1;
  /* only the trades inside the price record shape the axis; a 2016 sale
     restated to $14 must not drag a $100 to $500 chart down to $20 */
  const drawn=evs.filter(e=>{const dt=e.td||e.fd;return dt>=px[0][0]&&dt<=px[px.length-1][0];});
  /* LOG SCALE. A stock up 10x over five years is a flat line for four of
     them on a linear axis, and every early trade sits in the mud. */
  let lo=Infinity,hi=-Infinity;for(const p of px){if(p[1]<lo)lo=p[1];if(p[1]>hi)hi=p[1];}
  for(const e of drawn){const y=e.apa||null;if(y&&y>0){if(y<lo)lo=y;if(y>hi)hi=y;}}
  lo=Math.max(lo,1e-3);
  const L0=Math.log(lo)-(Math.log(hi)-Math.log(lo))*0.08,L1=Math.log(hi)+(Math.log(hi)-Math.log(lo))*0.12;
  const X=d=>pad.l+(Date.parse(d)-t0)/((t1-t0)||1)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(Math.log(v)-L0)/((L1-L0)||1)*(h-pad.t-pad.b);
  const ticks=[];
  for(let e=Math.floor(Math.log10(lo))-1;e<=Math.ceil(Math.log10(hi));e++)for(const m of [1,1.5,2,3,5,7]){const v=m*Math.pow(10,e);if(Math.log(v)>L0&&Math.log(v)<L1)ticks.push(v);}
  while(ticks.length>5){for(let i=ticks.length-2;i>=0;i-=2)ticks.splice(i,1);}
  /* the line: one point per trading day, thinned to the pixel */
  let d="",lastX=-9;const hover=[];
  for(const p of px){const x=X(p[0]);if(x-lastX<0.7&&d)continue;lastX=x;d+=(d?" L ":"M ")+x.toFixed(1)+" "+Y(p[1]).toFixed(1);}
  /* the trades nearest each day, for the crosshair */
  const byDay={};for(const e of drawn){const dt=e.td||e.fd;(byDay[dt]=byDay[dt]||[]).push(e);}
  for(const p of px){const tr=byDay[p[0]];let line2="";
    if(tr){const b=tr.filter(e=>e.c==="P"),sl=tr.filter(e=>e.c==="S");const sum=a=>a.reduce((t,e)=>t+(e.v||0),0);
      line2=[b.length?`bought ${money(sum(b))}`:"",sl.length?`sold ${money(sum(sl))}`:""].filter(Boolean).join(", ");}
    hover.push([p[0],dayLabel(p[0])+" · "+dollars(p[1]),line2]);}
  let out=`<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="the share price, with the chief executive's trades on it" class="fchart" ${hoverAttrs(hover,fr,t0,t1)}>
  <defs><linearGradient id="pxg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--ink)" stop-opacity="0.10"/><stop offset="1" stop-color="var(--ink)" stop-opacity="0"/></linearGradient>
  <clipPath id="pxc"><rect class="reveal" x="0" y="0" width="${w}" height="${h}"/></clipPath></defs>`;
  for(const v of ticks){const y=Y(v);
    out+=`<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w-pad.r}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out+=`<text x="${pad.l-8}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-family="var(--ui)" font-size="10.5" font-weight="500" fill="var(--faint)">${dollars(v)}</text>`;}
  out+=yearsAxis(X,t0,t1,fr);
  out+=`<path class="fill" clip-path="url(#pxc)" d="${d} V ${(h-pad.b).toFixed(1)} H ${X(px[0][0]).toFixed(1)} Z" fill="url(#pxg)"/>`;
  out+=`<path class="line" d="${d}" fill="none" stroke="var(--ink)" stroke-opacity="0.8" stroke-width="1.2" stroke-linejoin="round"/>`;
  const closeAt=dt=>{let v=px[0][1];for(const p of px){if(p[0]<=dt)v=p[1];else break;}return v;};
  out+=dots(drawn,X,Y,e=>{const dt=e.td||e.fd;return e.apa>0?[e.apa,` at ${dollars(e.apa)}${e.ap&&Math.abs(e.ap-e.apa)>0.005?` (filed at ${dollars(e.ap)}, before splits)`:""}`]:[closeAt(dt),` at the ${dollars(closeAt(dt))} close (price on the filing not restated)`];},fr);
  /* THE DOTS GO UNNAMED (2026-09-24): the small mono labels naming the
     newest sale and buy overlapped their neighbours in dense stretches;
     the cards above already name both dates, and every dot still speaks
     on hover. */
  const last=px[px.length-1];
  /* the last close, labelled above its point; when the point sits in the
     top of the range the label would cross the line's peak, so it goes
     below instead (Schmitz's $20.1 on a chart topping at $20) */
  const ly=Y(last[1])-9<pad.t+12?Y(last[1])+16:Y(last[1])-9;
  out+=`<text class="endlbl" x="${(X(last[0])-6).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="end" font-family="var(--ui)" font-size="11.5" font-weight="700" fill="var(--ink)">${dollars(last[1])}</text>`;
  out+=`<g class="xh" style="display:none"><line y1="${pad.t}" y2="${h-pad.b}" stroke="var(--ink)" stroke-opacity="0.35" stroke-dasharray="2 3"/><circle r="3.5" fill="var(--ink)"/><rect rx="3" fill="var(--ink)"/><text font-family="var(--ui)" font-size="10.5" font-weight="500" fill="#fff"></text><text font-family="var(--ui)" font-size="10.5" font-weight="500" fill="#fff"></text></g></svg>`;
  return out;
}
function stakeChart(pts,evs){
  const fr=frame(),{w,h,pad}=fr;
  const ms=monthEnds(pts);if(ms.length<2)return "";
  const t0=Date.parse(ms[0].d),t1=Date.parse(ms[ms.length-1].d)||t0+1;
  let lo=Infinity,hi=-Infinity;for(const o of ms){if(o.pct<lo)lo=o.pct;if(o.pct>hi)hi=o.pct;}
  let span=hi-lo;
  if(span<=Math.abs(hi)*1e-6){lo=hi*0.98;hi=hi*1.02;span=hi-lo;}   /* a flat record: a band, not a hairline */
  else{lo=Math.max(0,lo-span*0.12);hi=hi+span*0.14;}
  const X=d=>pad.l+(Date.parse(d)-t0)/((t1-t0)||1)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
  const ticks=[0,1,2,3].map(k=>lo+(hi-lo)*k/3);
  let dec=hi<10?2:1;const fmtAt=dc=>v=>v.toFixed(dc)+"%";
  while(dec<4&&new Set(ticks.map(fmtAt(dec))).size<ticks.length)dec++;
  const fmt=fmtAt(dec);
  let d="";ms.forEach((o,i)=>{const x=X(o.d),y=Y(o.pct);d+=i?` H ${x.toFixed(1)} V ${y.toFixed(1)}`:`M ${x.toFixed(1)} ${y.toFixed(1)}`;});
  const hover=ms.map((o,i)=>{const move=i?(Math.abs(o.dP)>1e-6?`${o.dP>0?"+":"−"}${Math.abs(o.dP).toFixed(2)} pts`:"no change"):"start";
    return [o.d,`${monthLabel(o.m)} · ${o.pct.toFixed(2)}% · ${compact(o.sh)} sh`,`${move}${o.why?" · "+o.why:""}`];});
  let out=`<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="the stake over time" class="fchart" ${hoverAttrs(hover,fr,t0,t1)}>
  <defs><linearGradient id="stg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--ink)" stop-opacity="0.10"/><stop offset="1" stop-color="var(--ink)" stop-opacity="0"/></linearGradient>
  <clipPath id="stc"><rect class="reveal" x="0" y="0" width="${w}" height="${h}"/></clipPath></defs>`;
  for(let k=0;k<=3;k++){const v=lo+(hi-lo)*k/3;const y=Y(v);
    out+=`<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w-pad.r}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out+=`<text x="${pad.l-8}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-family="var(--ui)" font-size="10.5" font-weight="500" fill="var(--faint)">${fmt(v)}</text>`;}
  out+=yearsAxis(X,t0,t1,fr);
  out+=`<path class="fill" clip-path="url(#stc)" d="${d} V ${(h-pad.b).toFixed(1)} H ${X(ms[0].d).toFixed(1)} Z" fill="url(#stg)"/>`;
  out+=`<path class="line" d="${d}" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linejoin="round"/>`;
  const at=dt=>{let v=ms[0].pct;for(const o of ms){if(o.d<=dt)v=o.pct;else break;}return v;};
  const drawn=evs.filter(e=>{const dt=e.td||e.fd;return dt>=pts[0][0]&&dt<=ms[ms.length-1].d;});
  out+=dots(drawn,X,Y,e=>[at(e.td||e.fd),""],fr);
  const lastO=ms[ms.length-1];
  const lyO=Y(lastO.pct)-9<pad.t+12?Y(lastO.pct)+16:Y(lastO.pct)-9;
  out+=`<text class="endlbl" x="${(X(lastO.d)-6).toFixed(1)}" y="${lyO.toFixed(1)}" text-anchor="end" font-family="var(--ui)" font-size="11.5" font-weight="700" fill="var(--accent)">${fmt(lastO.pct)}</text>`;
  out+=`<g class="xh" style="display:none"><line y1="${pad.t}" y2="${h-pad.b}" stroke="var(--ink)" stroke-opacity="0.35" stroke-dasharray="2 3"/><circle r="3.5" fill="var(--blue)"/><rect rx="3" fill="var(--ink)"/><text font-family="var(--ui)" font-size="10.5" font-weight="500" fill="#fff"></text><text font-family="var(--ui)" font-size="10.5" font-weight="500" fill="#fff"></text></g></svg>`;
  return out;
}
/* THE CROSSHAIR. One handler for both charts: the cursor's x becomes a
   date, the nearest row supplies the label, the box stays inside the
   frame. Touch works the same way. */
function attachHover(svg){
  const rows=JSON.parse(svg.getAttribute("data-rows")||"[]");if(!rows.length)return;
  const g=svg.querySelector(".xh");if(!g)return;
  const t0=+svg.dataset.t0,t1=+svg.dataset.t1,L=+svg.dataset.l,R=+svg.dataset.r,W=+svg.dataset.w,T=+svg.dataset.t,B=+svg.dataset.b,H=+svg.dataset.h;
  const line=g.querySelector("line"),dot=g.querySelector("circle"),box=g.querySelector("rect"),[t1El,t2El]=g.querySelectorAll("text");
  const path=svg.querySelector("path.line");
  const X=t=>L+(t-t0)/((t1-t0)||1)*(W-L-R);
  const times=rows.map(r=>Date.parse(r[0]));
  function yOnLine(x){
    /* walk the drawn path for the y at this x: cheap at a few hundred points */
    if(!path)return T;const n=path.getTotalLength();let a=0,b=n;
    for(let k=0;k<18;k++){const m=(a+b)/2;if(path.getPointAtLength(m).x<x)a=m;else b=m;}
    return path.getPointAtLength((a+b)/2).y;
  }
  function show(clientX){
    const r=svg.getBoundingClientRect();const x=(clientX-r.left)/r.width*W;
    if(x<L||x>W-R){g.style.display="none";return;}
    const t=t0+(x-L)/(W-L-R)*(t1-t0);
    let i=0;while(i<times.length-1&&Math.abs(times[i+1]-t)<Math.abs(times[i]-t))i++;
    const row=rows[i];const xx=X(times[i]);const yy=yOnLine(xx);
    line.setAttribute("x1",xx);line.setAttribute("x2",xx);dot.setAttribute("cx",xx);dot.setAttribute("cy",yy);
    t1El.textContent=row[1];t2El.textContent=row[2]||"";
    const w1=row[1].length*6.4,w2=(row[2]||"").length*6.4,bw=Math.max(w1,w2)+16,bh=row[2]?34:20;
    let bx=xx+10;if(bx+bw>W-R)bx=xx-10-bw;const by=Math.max(T,Math.min(yy-bh/2,H-B-bh));
    box.setAttribute("x",bx);box.setAttribute("y",by);box.setAttribute("width",bw);box.setAttribute("height",bh);
    t1El.setAttribute("x",bx+8);t1El.setAttribute("y",by+13.5);t2El.setAttribute("x",bx+8);t2El.setAttribute("y",by+28);
    g.style.display="";
  }
  svg.addEventListener("mousemove",e=>show(e.clientX));
  svg.addEventListener("mouseleave",()=>{g.style.display="none";});
  svg.addEventListener("touchstart",e=>{show(e.touches[0].clientX);},{passive:true});
  svg.addEventListener("touchmove",e=>{show(e.touches[0].clientX);},{passive:true});
}
/* ONE MOTION, ON LOAD: the line draws in and the shading under it is
   revealed to exactly the same x, frame by frame, then the dots appear.
   Once per render; a reader who asked for reduced motion gets the
   finished chart at once. */
function drawIn(svg){
  const path=svg.querySelector("path.line"),reveal=svg.querySelector("clipPath rect.reveal");
  if(!path)return;
  if(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches){svg.classList.add("drawn");return;}
  const n=path.getTotalLength();const T=900,t0=performance.now();
  svg.classList.add("animating");
  path.style.strokeDasharray=n;path.style.strokeDashoffset=n;
  if(reveal)reveal.setAttribute("width",0);
  function frame(now){
    const p=Math.min(1,(now-t0)/T),e=1-Math.pow(1-p,3);   /* ease-out */
    path.style.strokeDashoffset=n*(1-e);
    if(reveal)reveal.setAttribute("width",Math.max(0,path.getPointAtLength(n*e).x));
    if(p<1)requestAnimationFrame(frame);
    else{path.style.strokeDasharray="";path.style.strokeDashoffset="";if(reveal)reveal.setAttribute("width",svg.viewBox.baseVal.width);svg.classList.remove("animating");svg.classList.add("drawn");}
  }
  requestAnimationFrame(frame);
}
function recordBlock(r){
  const raw=HIST[r.tk];
  const px=PRICES_DAILY;
  const havePx=!!(px&&px.length>1),haveRec=!!(raw&&raw.length);
  /* the price with the trades on it opens the page (the view that shows
     whether a purchase caught a low); the stake over time is the toggle */
  let mode=window._chartMode||"price";
  if(mode==="price"&&!havePx)mode="pct";
  if(mode!=="price"&&!haveRec&&havePx)mode="price";
  /* the chips carry the only words: what each line is, on hover */
  const modes=[["price","Price","the share price: daily closes, split-adjusted. Dots sit at the price on the filing"],
               ["pct","Stake","the share of the company, one point per month-end: it moves when the holding changes and when the share count changes. Steps without a dot are grants, gifts, or the share count changing"]];
  const chips=`<div class="chips" role="group" aria-label="chart view">${modes.filter(m=>m[0]==="price"?havePx:haveRec).map(m=>`<button class="chip${mode===m[0]?" on":""}" onclick="setChartMode('${m[0]}')" title="${m[2]}">${m[1]}</button>`).join("")}</div>`;
  /* THE SECTION HAS A NAME (design v4): "When Elon Musk bought and sold",
     the toggle at its right; under the chart, the legend and one caption
     saying what the line is and what the toggle shows. */
  const head=`<h2>When ${esc(C.ceo||"the chief executive")} bought and sold</h2>`;
  /* the dots follow the table's filter: Bought draws purchases, Sold sales,
     All both; the other kinds have no dots to draw */
  const moving=EVENTS.filter(e=>e.tk===r.tk&&unchangedKind(e)===null&&(e.c==="P"||e.c==="S")
    &&(VIEW==="all"||(VIEW==="buys"&&e.c==="P")||(VIEW==="sells"&&e.c==="S")));
  const caption=mode==="price"
    ?`The trades against the share price.${haveRec?` Toggle to Stake for the position since ${esc(C.since||"2016")}.`:""}`
    :`The stake at each month-end since ${esc(C.since||"2016")}.${havePx?" Toggle to Price for the trades against the share price.":""}`;
  const key=`<div class="ckey">${moving.length?`<span class="b"><i></i>bought</span><span class="s"><i></i>sold</span>`:""}<span class="knote">${caption}</span></div>`;
  if(mode==="price"&&havePx){
    return `<div class="csec crec" data-nosnippet><div class="cshead">${head}${chips}</div>
      <div class="cchart">${priceChart(px,moving)}</div>${key}
    </div>`;
  }
  if(!haveRec)return "";
  const pts=cleanHist(r.tk);
  const series=pts.length>1?pts:raw;
  return `<div class="csec crec" data-nosnippet><div class="cshead">${head}${chips}</div>
    <div class="cchart">${stakeChart(series,moving)}</div>${key}
  </div>`;
}

/* ---- the trades ---- */
function tradesBlock(r){
  const all=EVENTS.filter(e=>e.tk===r.tk).sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||b.fd.localeCompare(a.fd));
  if(!all.length)return `<div class="csec"><h2>Trades</h2><div class="sub">No purchase or sale on record.</div></div>`;
  /* FIVE KINDS, NAMED FOR WHAT THE ROW IS, AND THE TAPE'S (2026-09-15):
     the group is tapeGroup, the badge is tapeKind, the grey word is
     tapeDetail, all shared with index.html so the two pages cannot drift.
     Bought and Sold are the market. Compensation is everything the company
     gave and what was sold of it: awards, exercises held or cashed, vests,
     withholding, forfeitures. Transfers are gifts, conversions and the
     rest. Share count is the company's own cover pages. */
  const kindOf=e=>e.cover?"covers":{bought:"buys",sold:"sells",comp:"comp",xfer:"transfers"}[tapeGroup(e)];
  const moved=e=>evMoved(e);
  /* THE SHARE COUNT IS A ROW TOO. Tesla's July 2026 10-Q raised the
     denominator from 3.76B to 3.95B and Musk's 29.91% became 28.44% with
     no filing of his; the table showed nothing between its top row and
     the card. Each cover page that moved the count is a row from the
     record: no trade, no value, the new denominator and the new percent. */
  const covers=((HIST[r.tk]||[]).filter(h=>/^(10-K|10-Q|20-F|40-F)/.test(h[8]||"")&&h[9])
    .map(h=>({cover:true,tk:r.tk,fd:h[0],td:h[0],tf:h[0],c:"",lb:"shares outstanding restated",form:h[8],os:h[9],ha:h[10],po:h[1],acc:h[11],
              u:h[11]&&r.cik?`https://www.sec.gov/Archives/edgar/data/${r.cik}/${h[11].replace(/-/g,"")}/`:""})));
  const every=[...all,...covers].sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||(b.cover?1:0)-(a.cover?1:0));
  const count=k=>every.filter(e=>(k==="all"||kindOf(e)===k)&&(!BIG||moved(e))).length;
  const evs=every.filter(e=>(VIEW==="all"||kindOf(e)===VIEW)&&(!BIG||moved(e)));
  const chip=(v,lab,n)=>`<button class="chip${VIEW===v?" on":""}" onclick="VIEW='${v}';renderOpen(PANEL[0])">${lab} <small>${n}</small></button>`;
  /* WHAT THE TRADE WAS, IN WORDS. One column for one fact: the kind of
     trade and whether it was pre-scheduled come from the same label the
     pipeline wrote, so "Planned sale" is one cell, not a red pill and an
     adjective. Coloured by what it did to the stake. */
  const kind=e=>{
    /* ONE VOCABULARY FOR EVERY FILING, the tape's (2026-09-15): Bought,
       Discretionary, Planned, Sold (with "not stated": a sale filed before
       Form 4 had a plan box), Compensation, Transfer. The badge is the
       kind; the specific label the pipeline wrote, in the site's words
       (options cashed, gift, award granted), is the detail in grey after
       it. A pre-IPO catch-up keeps its own badge. */
    if(e.pre)return {t:e.c==="P"?"Pre-IPO purchase":"Pre-IPO sale",word:"",k:"neu",n:evBadge(e).n};
    const tk=tapeKind(e);
    const word=tapeDetail(e);   /* ONE RENDERER (2026-09-28): the tape's own detail, riders and all */
    return {t:KIND_WORD[tk],word,k:tk,n:kindNote(e)};
  };
  const cell=e=>{
    const p=evMove(e);const uk=unchangedKind(e);const kd=kind(e);
    const stkTxt=uk==="pre"?"pre-IPO":p?stakeChange(p.v,p.approx):(uk!==null?"unchanged":"not stated");
    const stkCls=p?(p.v>=0?"plus":"minus"):"";
    const span=e.tf&&e.tf!==e.td?`${e.tf} to ${e.td.slice(5)}`:(e.td||e.fd);
    return {kd,p,uk,stkTxt,stkCls,span};
  };
  /* THE RECORD OPENS AT 25 (2026-09-24): a decade of filings ran the page
     very long; the first twenty-five rows answer the visit, and one button
     unfolds the rest in place -- no window inside the window, so find-in-page
     and a phone's one scrollbar keep working. The export always carries
     every row. */
  const shownEvs=(TRADES_ALL||evs.length<=25)?evs:evs.slice(0,25);
  const rows=shownEvs.map(e=>{
    if(e.cover)return `<tr class="cov"><td class="kk"><span class="kind neu">SHARE COUNT</span></td>
      <td class="dt" title="the company restated its shares outstanding to ${fmt(e.os)} on this cover page; nothing of the chief executive's moved">restated by the company (${esc(e.form)}) · no trade</td>
      <td class="d">${e.fd}</td>
      <td class="n lv">&mdash;</td>
      <td class="n lv">&mdash;</td>
      <td class="n lv">&mdash;</td>
      <td class="n lv" title="shares held, per the record">${e.ha?fmt(e.ha):"&mdash;"}</td>
      <td class="n lv po">${e.po!==null&&e.po!==undefined?e.po.toFixed(e.po<1?3:2)+"%":"&mdash;"}</td>
      <td class="f">${e.u?`<a href="${filingPage(e.u)}" target="_blank" rel="noopener" title="the cover page, on EDGAR; dated ${e.fd}">${esc(e.form)} · ${e.fd.slice(5).replace("-","/")} ↗</a>`:""}</td></tr>`;
    const {kd,p,uk,stkTxt,stkCls,span}=cell(e);
    /* WHAT HAPPENED IS ONE CELL (design v4): the kind in plain ink -- "Open-
       market purchase", "Planned sale", "Options exercised, tax withheld" --
       with the trade's value folded in after a dot. What each filing did to
       the stake and the day's denominator stay in the tooltips and the
       export; the Stake column carries the level. */
    /* THE TAPE'S TWO WORDS, IN TWO COLUMNS (2026-09-27): the chip a reader
       clicked on the tape is the KIND cell, same word, same colour; the ty
       cell keeps only the detail and the dollars, clipped when long. */
    const preipo=kd.t&&kd.t.startsWith("Pre-IPO");
    const ck=preipo?["neu","PRE-IPO"]
      :e.c==="P"?["bought","PURCHASE"]
      :e.c==="S"?(kd.k==="comp"?["comp","COMPENSATION"]:["sold","SALE"])
      :[kd.k||"neu",(kd.t||"").toUpperCase()||"OTHER"];
    const words=preipo?kd.t:(kd.word||"");
    const amt=(e.c==="P"||e.c==="S")&&!e.fl&&e.v?money(e.v):"&mdash;";
    const ofh=p?`<span title="what this filing did to the stake, as a share of the stake before it${p.approx?"; approximate":""}">${stakeChange(p.v,p.approx).replace(/^≈ /,"≈").replace(/stake /,"")}</span>`:`<span class="nopr" title="${esc(moveWhy(e))}">${uk!==null&&uk!=="pre"?"unchanged":"&mdash;"}</span>`;
    return `<tr><td class="kk" title="${esc(kd.n)}"><span class="kind ${ck[0]}">${ck[1]}</span></td>
      <td class="dt" title="${esc(kd.n)}${!p?`; ${esc(moveWhy(e))}`:""}">${words?esc(words):"&mdash;"}</td>
      <td class="d" title="traded ${spanDay(e,d=>d)}; filed ${e.fd}${lagNote(e)}">${span}</td>
      <td class="n lv">${amt}</td>
      <td class="n sh ${e.c==="P"?"up":e.c==="S"?"down":(e.nc>=0?"up":"down")}">${e.c==="P"||(e.c!=="S"&&e.nc>=0)?"+":"−"}${fmt(e.sh)}</td>
      <td class="n ch">${ofh}</td>
      <td class="n lv" title="shares held at the end of this filing's day, per the record; filings on one day share it">${e.ha?fmt(e.ha):"&mdash;"}</td>
      <td class="n lv po" title="the stake at the end of the day: held over outstanding">${e.po!==null&&e.po!==undefined?e.po.toFixed(e.po<1?3:2)+"%":"&mdash;"}</td>
      <td class="f">${e.u?`<a href="${filingPage(e.u)}" target="_blank" rel="noopener" title="the filing, on EDGAR; filed ${e.fd}">Form 4 · ${e.fd.slice(5).replace("-","/")} ↗</a>`:""}</td></tr>`}).join("");
  /* the export is the same rows as text, in the same order */
  window.exportTrades=()=>{
    const head=["date_from","date_to","filed","type","value_usd","shares","stake_change_pct","held_after","shares_outstanding","owned_pct","filing"];
    const lines=[head.join(",")].concat(evs.map(e=>{
      if(e.cover)return [e.fd,e.fd,e.fd,`Shares outstanding restated (${e.form})`,"","","",e.ha||"",e.os||"",(e.po!==null&&e.po!==undefined)?e.po.toFixed(4):"",e.u||""].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(",");
      const {kd,p,uk}=cell(e);
      return [e.tf||e.td||e.fd,e.td||e.fd,e.fd,(kd.t||"")+(kd.word?(kd.t?" · ":"")+kd.word:""),e.fl?"":(e.v||""),(e.c==="P"?"":"-")+(e.sh||""),
              p?p.v.toFixed(4):(uk!==null?"0":""),e.ha||"",e.os||"",(e.po!==null&&e.po!==undefined)?e.po.toFixed(4):"",e.u||""].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(",");
    }));
    const blob=new Blob([lines.join("\n")],{type:"text/csv"});
    const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`${r.tk}-trades.csv`;a.click();
  };
  const bigChip=`<button class="chip big${BIG?" on":""}" onclick="BIG=!BIG;renderOpen(PANEL[0])" title="only the rows that moved the stake by at least 1% of what it was">Big moves only &ge; 1%</button>`;
  return `<div class="csec ctrades"><div class="thead"><h2>The record, filing by filing</h2><button class="export" onclick="exportTrades()" title="the rows below, as a CSV; it carries the value, the stake change and the denominator every row">Export CSV</button></div>
    <div class="tchips">${chip("all","All",count("all"))}${chip("buys","Bought",count("buys"))}${chip("sells","Sold",count("sells"))}${chip("comp","Compensation",count("comp"))}${chip("transfers","Transfers",count("transfers"))}${chip("covers","Share count",count("covers"))}<span class="tsep"></span>${bigChip}</div>
    ${rows?`<table><thead><tr><th class="kk">Kind</th><th class="dt">Detail</th><th>Traded</th><th class="n">Amount</th><th class="n">Shares</th><th class="n">Of holding</th><th class="n lv">Held after</th><th class="n">Stake</th><th class="f">Filing</th></tr></thead><tbody>${rows}</tbody></table>`:`<div class="sub">Nothing in this view.</div>`}
    ${evs.length>shownEvs.length?`<button class="chip tmore" onclick="TRADES_ALL=true;renderOpen(PANEL[0])">Show all ${evs.length} filings &darr;</button>`:""}
    ${VIEW==="comp"?`<div class="sub" style="margin-top:10px">Compensation: what the company gave and what was sold of it. Awards granted, options exercised and held or cashed, vests, tax withholding, forfeitures. None of it is counted as buying or selling in the site's summaries; what each did to the stake is in the row's tooltip and the export.</div>`:""}
    ${VIEW==="transfers"?`<div class="sub" style="margin-top:10px">Transfers: gifts, conversions between classes, pre-IPO catch-ups and other non-market transactions the filing reports.</div>`:""}
    ${VIEW==="sells"&&evs.some(e=>tapeKind(e)==="sold")?`<div class="sub" style="margin-top:10px">Not stated: Form 4 had no Rule 10b5-1 box before April 2023, so whether a sale filed before then was planned is not on the form. Every sale since is Discretionary or Planned.</div>`:""}
    ${VIEW==="covers"?`<div class="sub" style="margin-top:10px">Share count: the company's cover pages that changed the number of shares outstanding. The stake moves with them though nothing of the chief executive's did.</div>`:""}
  </div>`;
}

/* ---- the receipt for the badge ---- */
/* THE WATCH (PLAN.md sections 2 and 5): "email me if this founder buys on the
   open market or makes a discretionary sale." One is free, confirmed by a
   click; any number of names, each managed by the links in its own emails.
   The box sits under the record on every page, sealed or open: what a
   person does is not behind the seal, only what they own. */
let WATCHING=null;   /* the signed-in reader's watch on this company, once known */
/* THE FOURTH CARD (2026-09-17). The watch used to be a band under the
   numbers, taller than they were and louder than anything else on the
   page. It is now the last of the four cards: a label, a switch with the
   person's name, one line of fine print. The rule is the site's one
   definition of a move (the About page states it: a buy or a discretionary
   sale of any size, or any other filing that moves the stake 1% or more);
   the card says only "An email when the stake moves." A signed-out reader
   flips the switch and is asked for an email in the same card. */
function watchCard(r){
  const who=r.ceo||C.ceo||"this chief executive";
  const on=!!(WATCHING&&WATCHING.tk===r.tk);
  const q=new URLSearchParams(location.search).get("watch");
  const said={on:`You're watching ${who}.`,off:`Stopped. No more emails about ${who}.`,alloff:"Stopped. No more emails about anyone.",expired:"That link expired; ask again here."}[q];
  const fine=on?`You'll get an email when the stake moves.`:`Free. No account.`;
  /* THE FIELD FIRST (2026-09-24). A reader from a search typed the person's
     name; the card asks the one thing they want next, with the field in
     view. The switch is for a signed-in member, who is watching at once. */
  return `<div class="wcard" id="cwatch" title="a buy or a discretionary sale of any size, or any other filing that moves the stake 1% or more">
    <div class="wq">Get an email when ${esc(who)}'s stake moves.</div>
    <form class="wform" onsubmit="return watchThis('${r.tk}',event)"><input type="email" id="wemail" placeholder="you@email.com" required autocomplete="email" aria-label="Email address"><button class="wbtn" type="submit">Watch &rarr;</button></form>
    <div class="wfine" id="wfine">${said?`<b>${esc(said)}</b> `:""}${fine}</div>
  </div>`;
}
async function watchThis(tk,ev){
  if(ev)ev.preventDefault();
  /* TWO FORMS, ONE FLOW (design v4): the card beside the answer and the
     dark band at the page's foot both submit here; each reads its own
     field and writes its own fine print. */
  const form=ev&&ev.target&&ev.target.tagName==="FORM"?ev.target:document.querySelector("#cwatch .wform");
  const inp=form?form.querySelector("input[type=email]"):$("#wemail");
  const scope=form?form.parentElement:null;
  const f=(scope&&scope.querySelector(".wfine"))||$("#wfine");
  const btn=form?form.querySelector("button"):document.querySelector("#cwatch .wbtn");
  const email=inp?(inp.value||"").trim():"";
  if(!email)return false;
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk,ceo:C.ceo||"",email})});
    const j=await q.json();
    if(j.ok&&j.watching){WATCHING={tk};renderOpen(PANEL[0],{animate:false});}
    else if(j.ok){if(f)f.innerHTML=`<b>Sent.</b> ${esc(j.message||"Confirm from the email and the watch is on.")}`;}
    else{if(f)f.textContent=j.message||"That didn't work.";}
  }catch(e){if(f)f.textContent="Something went wrong; write to hello@founderledequities.com.";}
  return false;
}
/* THE SENTENCE, COPYABLE (distribution): the stake as of the filing, the
   record, the page's URL. A reader who pastes it into a group chat is
   carrying the number and the address; that is the site's marketing. */
function factSentence(r){
  const evs=EVENTS.filter(e=>e.tk===r.tk&&(e.c==="P"||e.c==="S")&&unchangedKind(e)===null&&!e.pre);
  const buys=evs.filter(e=>e.c==="P").length,sells=evs.length-buys;
  const co=r.co||C.co||r.tk,ceo=r.ceo||C.ceo||"the CEO";
  const who=(fInfo(r.tk)||{}).f==="yes"?"a founder":"hired";
  const asof=r.asof?new Date(r.asof+"T00:00:00Z").toLocaleDateString("en-US",{month:"short",day:"numeric",timeZone:"UTC"}):"";
  const stake=`${r.pct!==null&&r.pct!==undefined?(r.pct<1?r.pct.toFixed(3):r.pct.toFixed(2))+"%":"an unstated share"} of ${co}`;
  return `${ceo} owns ${stake} (${r.tk})${asof?` as of the ${asof} filing`:""}, ${who}. Since 2016: ${buys} open-market buy${buys===1?"":"s"}, ${sells} sale${sells===1?"":"s"} that moved the stake.\n${location.origin}/company/${r.tk}/`;
}
async function copyFact(r){
  const t=factSentence(r),m=$("#factmsg");
  try{await navigator.clipboard.writeText(t);if(m)m.textContent="Copied.";}
  catch(e){if(m)m.textContent=t;}
}
/* whyBlock left the page (2026-09-24): the badge asserts, the record earns
   the trust; the proxy evidence stays in founders.csv and the export. */

function reportBlock(r){
  const subj=encodeURIComponent(`${r.tk}: a figure looks wrong`);
  const body=encodeURIComponent(`Company: ${r.co} (${r.tk})\nWhat I see: \nWhat I think it should be: \nWhere I checked: \n\nPage: https://founderledequities.com/company/${r.tk}/`);
  return `Computed from SEC EDGAR, never estimated. Prices are the ${PRICES_ASOF||"latest"} close.
    If a number looks wrong, <a href="mailto:hello@founderledequities.com?subject=${subj}&body=${body}">say so</a>; every figure links to the filing it came from.`;
}

/* HOW THE STAKE IS HELD (2026-09-25): the same fixed fixture on every
   page. C.held arrives display-ready from the bake (verbatim vehicle text,
   class labels, stale flags); the bake put it there only when the rows
   summed to the published stake, so rendering it is the warranty restated.
   The Not counted expander moves into this section's footer when the
   section exists, so the number's assembly and its exclusions share one
   home; without the section it stays under the cards as before. */
function heldBlock(r,notCounted){
  /* the position statement: class bands (each with its own subtotal and
     last-stated filing), the direct line, then the vehicles -- an HELD
     INDIRECTLY sub-band with subtotal when there are 2+; folds live inside
     their group; the double rule closes the account (2026-09-25b) */
  const held=C.held||[];
  if(!held.length)return "";
  const want=held.reduce((t,x)=>t+(x.shares||0),0);
  const mon=d=>{try{const t=new Date(d+"T12:00:00");return t.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"});}catch(e){return d;}};
  const line=(x,text,ind)=>{
    let veh=text;
    if(x.stale&&x.as_of)veh+=` &middot; last stated ${esc(mon(x.as_of).replace(/ \d+,/,""))}`;
    return `<div class="hrow${x.stale?" hstale":""}"><div class="hveh${ind?" hind":""}">${veh}</div><div class="hsh">${fmt(x.shares)}</div><div class="hpc">${x.pct||""}%</div></div>`;
  };
  const byK={},order=[];
  for(const x of held){const k=x.klass||"Common stock";if(!byK[k]){byK[k]=[];order.push(k);}byK[k].push(x);}
  order.sort((a,b)=>byK[b].reduce((t,x)=>t+x.shares,0)-byK[a].reduce((t,x)=>t+x.shares,0));
  const flink=a=>{a=(a||"").replace(/-/g,"");return(a&&r&&r.cik)?` &middot; <a href="https://www.sec.gov/Archives/edgar/data/${r.cik}/${a}/" target="_blank" rel="noopener">Form 4 &nearr;</a>`:"";};
  let parts="";
  for(const k of order){
    const grp=byK[k].slice().sort((a,b)=>b.shares-a.shares);
    const gsum=grp.reduce((t,x)=>t+x.shares,0);
    const newest=grp.reduce((m,x)=>((x.as_of||"")>(m.as_of||"")?x:m),grp[0]);
    const lab=`${esc(k).toUpperCase()} <span class="hcd">&middot; stated ${esc(mon(newest.as_of||""))}${flink(newest.accession)}</span>`;
    const nums=order.length>1?`<div class="hsh">${fmt(gsum)}</div><div class="hpc">${(gsum/want*100).toFixed(1)}%</div>`:`<div class="hsh"></div><div class="hpc"></div>`;
    parts+=`<div class="hcband"><div class="hcl">${lab}</div>${nums}</div>`;
    /* two manners, one grammar (2026-09-25c): direct and indirect are
       sibling bands; plain rows only for actual vehicles, when 2+ */
    const direct=grp.filter(x=>(x.di||"").toUpperCase()!=="I"&&(x.vehicle||"").toLowerCase().startsWith("held directly"));
    const indirect=grp.filter(x=>!direct.includes(x));
    const bandRow=(label,xs,name)=>{
      const bsum=xs.reduce((t,x)=>t+(x.shares||0),0);
      const stale=xs.every(x=>x.stale);
      let lab=label;
      if(name!=null){lab+=` &middot; <span class="hvn">${esc(name)}</span>`;const x=xs[0];if(x.stale&&x.as_of)lab+=` &middot; last stated ${esc(mon(x.as_of).replace(/ \d+,/,""))}`;}
      return `<div class="hsub${stale?" hstale":""}"><div class="hveh">${lab}</div><div class="hsh">${fmt(bsum)}</div><div class="hpc">${(bsum/want*100).toFixed(1)}%</div></div>`;
    };
    if(direct.length)parts+=bandRow("HELD DIRECTLY",direct);
    if(indirect.length>=2){
      parts+=bandRow(`HELD INDIRECTLY &middot; ${indirect.length} VEHICLES`,indirect);
      const shown=HELD_ALL?indirect:indirect.slice(0,6);
      for(const x of shown)parts+=line(x,esc(x.vehicle||""),true);
      const rest=indirect.slice(6);
      if(!HELD_ALL&&rest.length)parts+=`<button class="chip hmore" onclick="HELD_ALL=true;renderOpen(PANEL[0])">${rest.length} more vehicle${rest.length===1?"":"s"} &middot; ${fmt(rest.reduce((t,x)=>t+(x.shares||0),0))} shares &darr;</button>`;
    }else if(indirect.length===1){
      parts+=bandRow("HELD INDIRECTLY",indirect,indirect[0].vehicle||"per the filing");
    }
  }
  const pct=(r&&r.pct!=null)?r.pct.toFixed(2)+"%":"";
  const hasof=order.length>1?"each class as its filings last stated it":`as of the ${esc(mon(held.map(x=>x.as_of||"").sort().pop()||""))} filing`;
  return `<section class="csec chold" id="chold">
    <div class="cshead"><h2>How the stake is held</h2><div class="hlbls" title="${hasof}"><span class="hsh">SHARES</span><span class="hpc">OF THE STAKE</span></div></div>
    <div class="hbox">${parts}<div class="htot"><div class="htl">THE STAKE</div><div class="hsh">${fmt(want)}</div><div class="hpc">${pct}</div></div></div>
    ${notCounted?`<div class="hsum">${notCounted}</div>`:""}
  </section>`;
}
function renderOpen(r,{animate=true}={}){
  window._lastRow=r;
  /* THE WATCH IS BESIDE THE ANSWER (2026-09-23): the head's right column,
     level with the H1 -- the page's one ask, where a searcher lands */
  const slot=$("#cwatchslot");if(slot)slot.innerHTML=watchCard(r);
  $("#cbody").innerHTML=band(r)+heldBlock(r,window.__notCounted||"")+recordBlock(r)+tradesBlock(r);
  const cr=$("#creport");if(cr)cr.innerHTML="";   /* the footer says where the numbers come from; the sentence that stood here was the same sentence */
  const svg=document.querySelector(".cchart svg.fchart");
  if(svg){attachHover(svg);if(animate)drawIn(svg);}
}

async function fetchText(paths){
  /* A PAGE IS NOT A FILE: the host answers an unknown path with the home
     page and a 200; a reply that starts like HTML is a miss and the next
     path is tried (2026-09-14: a shard that did not exist, and the
     stake chart parsed the home page). */
  for(const p of paths){try{const q=await fetch(withV(p));if(!q.ok)continue;const t=await q.text();if(/^\s*</.test(t))continue;return t;}catch(e){}}
  return null;
}

(async function main(){
  hit("view","page");   /* THE PAGE COUNTS ITS OWN VISITORS, like the home page: the same beacon, shared */
  let row=C.row?mapPanel([C.row])[0]:null;
  if(!row){
    /* a company whose record could not settle on a figure: the same page,
       the honest empty figures, the filings in the table */
    row={tk:C.tk,co:C.co,ceo:C.ceo,pct:null,sh:null,out:C.out||null,oasof:C.oasof||"",asof:"",conf:"medium",tabled:null};
  }
  if(C.price){row.price=C.price;row.val=row.sh?row.sh*C.price:null;PRICES_ASOF=C.price_date||"";}
  setRow(row);
  renderOpen(row,{animate:false});   /* the numbers first; the record and trades fill in */
  /* ONE TREE (2026-09-23): every company's full record and trades live at
     the root; the shards carry everything since 2016. */
  const [h,e,p]=await Promise.all([
    fetchText([`/history/${C.tk}.csv`]),
    fetchText([`/events/${C.tk}.csv`]),
    fetchText([`/prices/${C.tk}.csv`])]);
  if(h){const m=mapHistory(parseCSV(h));if(m[C.tk])HIST=m;}
  if(e){EVENTS=mapEvents(parseCSV(e)).filter(x=>x.tk===C.tk);}
  if(p){PRICES_DAILY=parseCSV(p).map(r=>[String(r.date||"").slice(0,10),num(r.close)]).filter(x=>x[0].length===10&&x[1]>0);if(!PRICES_DAILY.length)PRICES_DAILY=null;}
  renderOpen(row);
})();

function setChartMode(m){window._chartMode=m;if(window._lastRow)renderOpen(window._lastRow);}
let _rsz=null;window.addEventListener("resize",()=>{clearTimeout(_rsz);_rsz=setTimeout(()=>{if(window._lastRow)renderOpen(window._lastRow,{animate:false});},150);});
