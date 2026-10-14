/* The header search (2026-09-23). One box in the topnav on every page,
   one index behind it: /search.json, a list of {t,c,e,p,f,v} rows written
   by ops/build_company_pages.py from tonight's panel -- ticker, company,
   CEO, stake %, founder flag, stake value (for ranking). Nothing here
   depends on the page's other scripts: 404.html and every built company
   page load this file alone, so it carries its own escaping and fetch.

   Behaviour: the index loads on first focus (nobody pays for it who never
   touches the box); typing matches ticker prefix, then company and CEO
   substrings; ranking is ticker-exact first, then founders, then stake
   value. Arrows move, Enter opens the highlighted row (the top one by
   default), Escape closes, and "/" anywhere on the page focuses the box. */
(function(){
"use strict";
/* EVERY BOX IS LIVE (2026-10-14). The nav's box used to hide on the home
   and alerts pages because this file bound one box, and those pages carry
   a big one of their own; the nav's links then shifted between pages. The
   index is loaded once and shared; each box gets its own rows and
   highlight. "/" focuses the page's big box when it has one, else the nav's. */
var IDX=null,LOADING=null;
const DATA_V="dev";   /* stamped by ops/deploy.sh, like every data-loading script: the deploy sed matches the const spelling exactly */
var esc=function(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");};
function load(){
  if(IDX||LOADING)return LOADING;
  LOADING=fetch("/search.json?v="+encodeURIComponent(DATA_V),{cache:"force-cache"})
    .then(function(q){return q.ok?q.json():null;})
    .then(function(j){IDX=(j&&j.rows)||[];return IDX;})
    .catch(function(){IDX=[];return IDX;});
  return LOADING;
}
function match(q){
  q=q.trim().toLowerCase();
  if(!q||!IDX)return[];
  var out=[],i,r,tk,co,ceo;
  for(i=0;i<IDX.length;i++){
    r=IDX[i];tk=r.t.toLowerCase();co=(r.c||"").toLowerCase();ceo=(r.e||"").toLowerCase();
    var s=-1;
    if(tk===q)s=0;                       /* the ticker, exactly */
    else if(tk.indexOf(q)===0)s=1;       /* a ticker being typed */
    else if(co.indexOf(q)>=0||ceo.indexOf(q)>=0)s=2;   /* a name */
    if(s>=0)out.push([s,r.f?0:1,-(r.v||0),i,r]);
  }
  out.sort(function(a,b){return a[0]-b[0]||a[1]-b[1]||a[2]-b[2]||a[3]-b[3];});
  return out.slice(0,8).map(function(x){return x[4];});
}
/* A BOX CAN DO SOMETHING OTHER THAN NAVIGATE (2026-10-14): a box with
   data-pick="name" hands the chosen row to window[name](row); if that
   returns true the pick is handled there (the alerts page adds a watch
   from its box), otherwise the company page opens as always. */
function bind(box,dd){
  var SEL=0,ROWS=[],pickName=box.getAttribute("data-pick");
  function open(r){
    var h=pickName&&window[pickName];
    if(h&&h(r)===true){close();box.value="";return;}
    location.href="/company/"+encodeURIComponent(r.t)+"/";
  }
  function paint(){
    if(!ROWS.length){dd.innerHTML="";dd.style.display="none";return;}
    dd.innerHTML=ROWS.map(function(r,i){
      var pct=r.p===null||r.p===undefined||r.p===""?"":(r.p<1?Number(r.p).toFixed(2):Number(r.p).toFixed(1))+"%";
      return '<a class="qrow'+(i===SEL?" on":"")+'" data-i="'+i+'" href="/company/'+encodeURIComponent(r.t)+'/">'
        +'<span class="qtk">'+esc(r.t)+'</span><span class="qco">'+esc(r.c||"")+'</span>'
        +'<span class="qceo">'+esc(r.e||"")+'</span>'
        +(pct?'<span class="qpct">'+pct+'</span>':"")
        +(r.f?'<span class="qf">FOUNDER-LED</span>':"")
        +'</a>';
    }).join("");
    dd.style.display="block";
  }
  function go(){
    var r=ROWS[SEL]||ROWS[0];
    if(r)open(r);
  }
  function close(){ROWS=[];SEL=0;paint();}
  dd.addEventListener("click",function(ev){
    var a=ev.target.closest?ev.target.closest("a.qrow"):null;
    if(!a||!pickName)return;
    var r=ROWS[Number(a.getAttribute("data-i"))];
    if(r){ev.preventDefault();open(r);}
  });
  box.addEventListener("focus",function(){load();});
  box.addEventListener("input",function(){
    var q=box.value;
    load().then(function(){ROWS=match(q);SEL=0;paint();});
  });
  box.addEventListener("keydown",function(ev){
    if(ev.key==="ArrowDown"){SEL=Math.min(SEL+1,ROWS.length-1);paint();ev.preventDefault();}
    else if(ev.key==="ArrowUp"){SEL=Math.max(SEL-1,0);paint();ev.preventDefault();}
    else if(ev.key==="Enter"){if(ROWS.length){go();ev.preventDefault();}}
    else if(ev.key==="Escape"){close();box.blur();}
  });
  document.addEventListener("click",function(ev){
    if(!dd.contains(ev.target)&&ev.target!==box)close();
  });
}
var pairs=[["hq","hqd"],["navq","navqd"]],first=null,i;
for(i=0;i<pairs.length;i++){
  var b=document.getElementById(pairs[i][0]),d=document.getElementById(pairs[i][1]);
  if(b&&d){bind(b,d);if(!first)first=b;}
}
if(first)document.addEventListener("keydown",function(ev){
  if(ev.key==="/"&&document.activeElement!==first
     &&!/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||"")){
    first.focus();ev.preventDefault();
  }
});
})();
