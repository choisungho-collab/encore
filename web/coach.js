/* ENCORE 코치 엔진 — match.html · player.html 공용 */
const COACH_SUPPLY={"Zergling":.5,"Hydralisk":1,"Mutalisk":2,"Lurker":2,"Scourge":.5,"Ultralisk":4,"Defiler":2,"Queen":2,"Guardian":2,"Devourer":2,"Drone":1,"Marine":1,"Firebat":1,"Medic":1,"Ghost":1,"SCV":1,"Vulture":2,"Siege Tank (Tank Mode)":2,"Siege Tank (Siege Mode)":2,"Goliath":2,"Wraith":2,"Valkyrie":3,"Dropship":2,"Science Vessel":2,"Battlecruiser":6,"Zealot":2,"Dragoon":2,"High Templar":2,"Dark Templar":2,"Archon":4,"Dark Archon":4,"Reaver":4,"Shuttle":2,"Observer":1,"Scout":3,"Corsair":2,"Carrier":6,"Arbiter":4,"Probe":1};
const COACH_WORKERS=new Set(["SCV","Drone","Probe"]);
const COACH_GAS=new Set(["Refinery","Assimilator","Extractor"]);
const COACH_PROD={"T":new Set(["Barracks","Factory","Starport"]),"P":new Set(["Gateway","Robotics Facility","Stargate"]),"Z":new Set(["Hatchery","Lair","Hive"])};
const COACH_WIN_TECH={"Z":{"Defiler":"디파일러","Lurker":"러커","Ultralisk":"울트라","Guardian":"가디언"},"T":{"Science Vessel":"사이언스베슬","Siege Tank (Tank Mode)":"시즈탱크","Battlecruiser":"배틀크루저"},"P":{"High Templar":"하이템플러","Archon":"아콘","Reaver":"리버","Arbiter":"아비터","Carrier":"캐리어"}};
const COACH_UKR={"Marine":"마린","Firebat":"파벳","Medic":"메딕","Vulture":"벌처","Goliath":"골리앗","Wraith":"레이스","Dropship":"드랍십","Science Vessel":"베슬","Valkyrie":"발키리","Battlecruiser":"배틀","Ghost":"고스트","Siege Tank (Tank Mode)":"탱크","Siege Tank (Siege Mode)":"탱크","Zealot":"질럿","Dragoon":"드라군","High Templar":"하템","Dark Templar":"다크","Archon":"아콘","Reaver":"리버","Corsair":"커세어","Carrier":"캐리어","Arbiter":"아비터","Scout":"스카웃","Shuttle":"셔틀","Zergling":"저글링","Hydralisk":"히드라","Mutalisk":"뮤탈","Lurker":"러커","Ultralisk":"울트라","Defiler":"디파일러","Guardian":"가디언","Devourer":"디바우러","Scourge":"스컬지","Queen":"퀸"};
const COACH_RACEKR={"T":"테란","P":"토스","Z":"저그","R":"랜덤"};
function pyRound(x){const f=Math.floor(x),d=x-f;if(d<0.5)return f;if(d>0.5)return f+1;return (f%2===0)?f:f+1;}
function _coach_race(r,unames){
  r=(r||"").toLowerCase();
  if(r.indexOf("toss")>=0||r.indexOf("prot")>=0)return "P";
  if(r.indexOf("zerg")>=0)return "Z";
  if(r.indexOf("terr")>=0)return "T";
  if(r==="p"||r==="pro")return "P";
  if(r==="z"||r==="zer")return "Z";
  if(r==="t"||r==="ter")return "T";
  if(unames&&unames.length){const n=new Set(unames);const hit=a=>a.some(x=>n.has(x));
    if(hit(["SCV","Marine","Vulture","Goliath","Wraith","Siege Tank (Tank Mode)","Siege Tank"]))return "T";
    if(hit(["Probe","Zealot","Dragoon","Dark Templar","Carrier","Corsair"]))return "P";
    if(hit(["Drone","Zergling","Hydralisk","Mutalisk","Lurker"]))return "Z";}
  return "T";
}
function _coach_first(build,names){for(const b of build){if(names.has(b.name))return b.t;}return null;}
function _s2(s){var q=(""+(s||"0:0")).split(":");return (+q[0])*60+(+q[1]||0);}
function prodTarget(race,mins,maxSup){
  var t;
  if(mins<5)       t={T:3,P:3,Z:4}[race];
  else if(mins<7)  t={T:5,P:6,Z:6}[race];
  else if(mins<9)  t={T:7,P:8,Z:8}[race];
  else if(mins<13) t={T:9,P:10,Z:10}[race];
  else             t={T:11,P:12,Z:11}[race];
  if(maxSup>=160)  t=Math.max(t,{T:9,P:9,Z:9}[race]);
  return t||4;
}
function coach_player(p,peers,mins,fast){
  mins=mins||0;
  var unames=(p.units||[]).map(function(u){return u.name;});
  var race=_coach_race(p.race,unames);var build=p.build||[];
  var units={};(p.units||[]).forEach(function(u){units[u.name]=u;});
  var bnames=new Set(build.map(function(b){return b.name;}));
  var pts=[];
  var T=function(tone,k,ti,tx){pts.push({tone:tone,k:k,t:ti,x:tx});};
  var gas=_coach_first(build,COACH_GAS);
  var prodN=(p.main_prod_n!=null)?p.main_prod_n:build.filter(function(b){return COACH_PROD[race].has(b.name);}).length;
  var prodKo=p.main_prod_ko||({T:"배럭",P:"게이트",Z:"해처리"}[race]||"생산건물");
  var ups=build.filter(function(b){return b.cat==="upgrade"||b.cat==="tech";});var up_n=ups.length;var up1=ups.length?ups[0].t:null;
  var exp=(p.townhalls&&p.townhalls.length)?p.townhalls[0].t:null;
  var maxSup=p.max_supply||0;var tc=(p.townhalls||[]).length;
  var workers=0;Object.keys(units).forEach(function(n){if(COACH_WORKERS.has(n))workers+=units[n].n;});
  var army=0;Object.keys(units).forEach(function(n){if(!COACH_WORKERS.has(n))army+=units[n].n*(COACH_SUPPLY[n]||1);});
  var marine=(units["Marine"]||{}).n||0,medic=(units["Medic"]||{}).n||0,fbat=(units["Firebat"]||{}).n||0;
  var enemyP=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team&&pe.race==="P";}).length;
  var A=p.atk_lv||0,R=p.arm_lv||0,mxlv=Math.max(A,R),haslv=(p.atk_lv!=null||p.arm_lv!=null);
  var apm=p.apm,eapm=p.eapm,series=p.apm_series||[0];
  var wt=COACH_WIN_TECH[race];var have_wt=Object.keys(wt).filter(function(n){return units[n];}).map(function(n){return wt[n];});
  var raceKr=COACH_RACEKR[race];
  var timings={gas:gas,prod:prodN,up_n:up_n,up1:up1,exp:exp,army:pyRound(army),workers:workers,max_supply:p.max_supply,supply200:p.supply200,total_supply:p.total_supply,tcount:tc,atk_lv:p.atk_lv,arm_lv:p.arm_lv,supply_bld:p.supply_bld,supply_ko:p.supply_ko,main_prod_n:p.main_prod_n,main_prod_ko:p.main_prod_ko,scout_first:p.scout_first,scouted:p.scouted,atk_first:p.atk_first,groups:p.groups,drops:p.drops,prod_max_gap:p.prod_max_gap,prod_active:p.prod_active};

  // 1. 생산기지·리맥스 (최우선)
  var tgt=prodTarget(race,mins,maxSup);
  if(prodN>=tgt){
    T("good","prod",prodKo+" "+prodN+"개 — 생산·리맥스 탄탄","생산기지를 충분히 지었어. 이 시간대 "+raceKr+" 권장이 "+tgt+"개인데 "+prodN+"개 확보 — 한타에서 병력이 갈려도 금방 다시 꽉 채울 수 있어. 한 방 병력보다 '죽자마자 다시 채우는' 리맥스 속도가 물량전 최상위 핵심이야.");
  }else if(prodN<Math.max(2,tgt*0.6)){
    T("warn","prod",prodKo+" "+prodN+"개 — 생산기지 부족","이 시간대 "+raceKr+"는 "+prodKo+" "+tgt+"개 정도가 기준인데 "+prodN+"개뿐이야. 물량전에선 돈이 남는 건 생산 구조가 부족하다는 신호 — 병력이 한 번 갈리면 리맥스가 너무 느려서 게임이 터져. 돈 남기 전에 "+prodKo+"부터 늘리자.");
  }else{
    T("tip","prod",prodKo+" "+prodN+"개 — 조금 부족","권장 "+tgt+"개에 살짝 못 미쳤어. "+prodKo+"를 2~3개만 더 지으면 한타 직후 리맥스가 눈에 띄게 빨라져. 물량전은 생산기지 수가 곧 회복력이야.");
  }

  // 2. 업그레이드
  var usyn="";
  if(units["Goliath"]&&mxlv<2) usyn=" 특히 골리앗은 공업이 생명 — 공2업이면 어택땅만으로도 캐리어 인터셉터를 녹여.";
  else if(units["Marine"]&&mxlv===0) usyn=" 마린은 공1업만 돼도 화력이 확 올라가 뮤탈·소수 병력 정리가 쉬워져.";
  else if(race==="Z"&&(units["Hydralisk"]||units["Zergling"])&&mxlv<2) usyn=" 히드라·저글링은 수가 많은 만큼 공업 한 단계가 전체 화력으로 곱해져 들어가.";
  if(haslv){
    var ut="업그레이드 공"+A+"·방"+R;
    if(mxlv===0)      T("warn","up",ut,"공·방 업그레이드가 하나도 없어. 물량전은 풀업 화력 싸움이라 1업만 차이나도 교전이 통째로 갈려. 가스 올라가자마자 업글부터 돌리자."+usyn);
    else if(mxlv<=1) T("tip","up",ut,"업글 단계가 낮아. 같은 병력도 풀업이면 화력이 확 달라져 — 병력 뽑으면서 공·방을 3업까지 꾸준히 올리자."+usyn);
    else if(mxlv>=3) T("good","up",ut,"공·방을 3업까지 올렸네. 풀업 화력 싸움의 핵심을 제대로 챙겼어 — 업글 차이는 곧 한타 차이야.");
    else             T("good","up",ut,"공·방 업글을 꾸준히 돌렸어. 3업까지 마저 채우면 같은 병력으로도 더 세져.");
  }else if(up_n===0){
    T("warn","up","업그레이드 없음","공·방 업그레이드가 없어. 풀업 화력 싸움인 물량전에선 1업 차이도 크게 갈려 — 가스 올라가면 업글부터.");
  }

  // 3. 종족별 결정타 (문서 금지사항 기반)
  if(race==="Z"){
    if(!units["Lurker"]&&!units["Defiler"]) T("tip","comp","러커가 없음","저그는 럴커가 나오기 전까진 계속 수세야. 럴커가 입구·센터·드랍 방어 라인을 잡아줘야 끌려다니지 않아 — 히드라 모이면 럴커부터 챙기자.");
    var hiveTech=units["Defiler"]||units["Ultralisk"]||units["Guardian"];
    if(mins>=12&&!hiveTech) T("warn","comp","후반인데 하이브 카드가 없음","12분이 넘으면 '온리 히드라'로는 200 한타에서 저그가 그냥 녹아 — 저그가 제일 약해지는 길이야. 디파일러 다크스웜으로 한타를 막거나, 가디언·울트라로 화력을 더해야 해. 하이브 올려 디파일러부터 챙기자.");
    else if(mins>=9&&mins<12&&!hiveTech) T("tip","comp","하이브 전환 준비할 때","곧 히드라만으론 부족해지는 구간이야. 12분 전후로 하이브를 올려 디파일러(다크스웜)나 가디언·울트라를 준비하면 후반 한타가 확 강해져.");
  }else if(race==="T"){
    var hasTank=units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"];
    if(mins>=8&&!hasTank) T("warn","comp","탱크 없이 바이오닉만","마린·메딕만으론 상대 캐논·성큰·럴커 라인을 못 뚫고 그냥 녹아. 탱크로 라인을 밀어야 해 — 팩토리 2개 이상 돌려 시즈탱크를 확보하자.");
    if(mins>=9&&!units["Science Vessel"]) T("tip","comp","베슬이 없음","베슬이 없으면 디파일러 스웜·하템 스톰·클로킹·드랍 대응이 약해. 베슬 2~3기는 챙겨야 후반 안정성이 확 올라가.");
    if(marine>=12&&medic===0&&mins>=5) T("warn","comp","메딕 없이 마린만","바이오닉의 핵심은 메딕이야. 메딕 없는 마린은 럴커·스톰·탱크에 순식간에 녹아 — 마린 한 부대(12)당 메딕 3~4기는 꼭 붙이자.");
    else if(marine>=12&&enemyP>=2&&fbat===0) T("tip","comp","파벳이 없음 (상대 토스 "+enemyP+"명)","상대에 토스가 많아. 발업 질럿엔 파벳이 특효라 마린 부대에 파벳 3기쯤 섞으면 교전이 훨씬 수월해져 — 메딕·파벳 비율만 맞춰도 바이오닉이 단단해져.");
  }else if(race==="P"){
    if(!units["High Templar"]&&!units["Archon"]) T(mins>=7?"warn":"tip","comp","하템(스톰)이 없음","질럿·드라군만으론 상대 덩어리 병력을 한 번에 정리할 수단이 없어. 토스가 제일 약해지는 게 '하템 없이 질드라만' 찍는 흐름이야 — 템플러 아카이브 올려 스톰 한 방을 챙기면 한타가 통째로 뒤집혀.");
    if(units["Zealot"]&&!units["Dragoon"]) T("tip","comp","드라군 없이 질럿만","질럿만으론 대공·중거리가 비어서 뮤탈·캐리어·탱크 라인에 약해. 드라군을 섞어 사거리와 대공을 받쳐주자.");
    if(p.drops!=null&&(p.drops||0)<1&&!(p.atk_first&&_s2(p.atk_first)<=360)&&mins>=8) T("tip","harass","견제가 적었음","빨무에서 토스가 제일 센 이유는 견제야. 질럿 와리가리로 상대를 흔들고 하템으로 일꾼을 지지면 상대 한 명이 휘청해 — 10분 전까진 센터 한타보다 견제로 이득 보는 게 토스의 일이야.");
  }
  if(have_wt.length) T("good","tech","결정타 확보: "+have_wt.join(", "),"상위 테크 유닛을 챙겼네. 물량전 후반은 이 게임체인저 유무로 갈려 — 좋은 판단이야.");

  // 4. 감지
  if(race==="P"&&!units["Observer"]&&!bnames.has("Photon Cannon")){
    T("warn","det","감지 수단 없음","옵저버도 포토캐논도 안 보여. 상대 다크·러커·벌처 마인을 못 보면 병력이 그냥 녹아 — 옵저버 1~2기는 필수야.");
  }else if(race==="T"&&!units["Science Vessel"]&&!bnames.has("Missile Turret")){
    T("tip","det","감지 수단 부족","베슬도 터렛도 안 보여. 다크·러커·클로킹·드랍 대비로 터렛이나 베슬을 챙겨두는 게 안전해.");
  }

  // 5. 멀티 (빨무에선 자원 무한이라 멀티 조언이 무의미 → 건너뜀)
  if(!fast&&race!=="Z"){
    if(tc>=2) T("good","exp","멀티 "+tc+"개 확보","멀티를 잡았네. 일꾼 생산처가 많을수록 견제로 일꾼이 잘려도 빨리 복구되고 물량도 빨라져 — 좋은 판단이야.");
    else if(mins>=6) T("tip","exp","본진 하나 — 멀티 권장","일꾼 생산기지가 본진 하나뿐이야. 드랍/스플래시로 모인 일꾼이 한 번에 몰살되면 본진 하나로는 복구가 느려 — 멀티로 생산기지를 늘리면 훨씬 안전해.");
  }

  // 6. 첫 200 / 물량
  if(maxSup>=190){
    if(have_wt.length) T("good","army","최대 ~"+Math.round(maxSup)+" 풀 병력","인구를 거의 꽉 채워 큰 한방을 굴렸고 결정타 유닛도 챙겼어 — 제대로 된 200이야. 채운 채 가만히 있으면 손해니 풀업 갖춰지면 바로 진출하자.");
    else T("tip","army","최대 ~"+Math.round(maxSup)+" — 조합은 아쉬움","인구는 꽉 채웠는데 게임체인저 유닛이 없어. 중요한 건 '빠른 200'이 아니라 '조합이 된 200'이야 — 물량 다음은 결정타 유닛 전환이야.");
  }else if(mins>=9&&maxSup<130){
    T("tip","army","최대 ~"+Math.round(maxSup)+" — 물량 부족","9분이 넘었는데 최대 병력이 적은 편이야. 생산기지를 늘려 남는 자원을 병력으로 더 빨리 전환하면 같은 시간에 훨씬 두꺼운 물량이 나와.");
  }

  // 7. 일꾼 (빨무에선 일꾼 수 조언이 무의미 → 건너뜀; 빨무 전용 팁에서 따로)
  if(!fast){
  if(workers>=40) T("good","worker","일꾼 "+workers+"기 — 경제 탄탄","일꾼을 넉넉히 뽑았네. 일꾼=돈=병력이라 경제 기반이 좋으면 병력·업글이 빨라져.");
  else if(workers<22&&mins>=5) T("tip","worker","일꾼 "+workers+"기 — 부족","일꾼이 적은 편이야. 물량전은 일꾼을 넉넉히(~50기) 꾸준히 뽑아야 돈이 넘쳐서 물량이 터져 — 잘려도 바로 다시 채우자.");
  }

  // 8. APM
  if(series.length>=3){
    var body=series.length>3?series.slice(0,-1):series;
    var sorted=body.slice().sort(function(a,b){return a-b;});
    var med=body.length?sorted[Math.floor(body.length/2)]:0;
    var dip=[];body.forEach(function(v,i){if(med>0&&v<med*0.55)dip.push(i);});
    if(dip.length) T("tip","apm",dip[0]+"분에 손이 멈춤","이 구간 APM이 평소("+med+")의 절반 아래로 떨어졌어. 교전에 집중하다 생산이 끊겼을 가능성이 커 — 부대지정+생산 단축키로 싸우면서 뽑기를 연습하면 이 공백이 사라져. 생산은 교전 중에도 안 끊기는 게 A급이야.");
  }
  if(apm&&eapm&&apm-eapm>=70){
    T("tip","apm","APM "+apm+" / 유효 "+eapm,"실제 명령(EAPM)에 비해 전체 APM이 높아 — 같은 곳 반복클릭이 많다는 뜻. 손은 빠르니 그 손을 생산·멀티 분배에 쓰면 실질 효율이 올라가.");
  }

  // 9. 정찰 (빨무에선 정찰 타이밍이 무의미 → 건너뜀)
  if(!fast&&p.scouted!=null){
    if(p.scouted===0||!p.scout_first){
      T("tip","scout","정찰을 거의 안 함","상대 본진을 일찍 못 보면 다크·드랍·올인 같은 빌드를 모르고 당해. 초반에 일꾼이나 빠른 유닛으로 상대 생산기지·테크를 한 번은 확인하자 — 정찰은 곧 대응이야.");
    }else if(_s2(p.scout_first)<150){
      T("good","scout","초반 정찰 "+p.scout_first+(p.scouted>1?" ("+p.scouted+"곳)":""),"일찍 정찰 들어갔네 — 상대 빌드를 보고 대응할 시간을 벌었어. 본 정보로 다음 수를 예측하는 게 핵심이야.");
    }else if(_s2(p.scout_first)>240){
      var _std=race==="Z"?"오버로드 2기 직후":"첫 파일런/서플 직후";
      T("tip","scout","정찰이 늦음 "+p.scout_first,"첫 정찰이 "+p.scout_first+"로 늦었어 — 정찰은 "+_std+"가 표준이야. 늦게 보면 상대 빌드에 대응할 시간이 줄어 초반에 휘둘려. 정찰은 곧 대응이야.");
    }
  }
  // 10. 컨트롤 그룹
  if(p.groups!=null&&p.groups<=2){
    T("tip","ctrl","컨트롤 그룹 "+p.groups+"개","병력·생산건물·마법유닛을 컨트롤 그룹으로 나눠 잡으면 싸우면서 동시에 생산이 돌아가. 그룹을 거의 안 쓰면 교전 중에 생산이 끊기기 쉬워.");
  }else if(p.groups!=null&&p.groups>=6){
    T("good","ctrl","컨트롤 그룹 "+p.groups+"개","컨트롤 그룹을 세분화해서 썼네 — 주력·생산·마법유닛을 분리 운용하는 상급 조작이야.");
  }
  // 11. 드랍 견제
  if(p.drops&&p.drops>=3){
    T("good","drop","드랍 견제 "+p.drops+"회","드랍으로 상대를 흔들었네 — 일꾼·생산기지를 때리거나 병력 회군을 유도하는 건 물량전에서 큰 이득이야. 정면 압박과 같이 쓰면 더 강해.");
  }
  // 12. 생산 연속성 (가동률/자원 소비율)
  if(p.prod_max_gap&&p.prod_max_gap>=90){
    T("tip","cont","생산 공백 최대 "+p.prod_max_gap+"초","한동안 유닛 생산이 끊긴 구간이 있어. 그때 자원이 쌓였을 가능성이 커 — 돈이 남는 건 생산기지가 부족하거나 생산이 멈췄다는 신호야. 교전 중에도 생산 단축키로 계속 찍는 게 가동률 A급이야.");
  }else if(p.prod_max_gap!=null&&p.prod_max_gap<=35&&(p.total_supply||0)>80){
    T("good","cont","생산 거의 안 끊김","유닛 생산 공백이 거의 없었어(최대 "+p.prod_max_gap+"초) — 교전 중에도 물량을 계속 뽑은 가동률 최상급이야.");
  }

  // 13. 상대 대비 비교 (1v1) — 같은 판 상대와 직접 비교가 가장 구체적인 코칭
  var oppList=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team;});
  if(oppList.length===1){
    var opp=oppList[0];
    if(!fast){var dw=(opp.workers||0)-workers;
    if(dw>=15) T("warn","vs","일꾼이 상대보다 "+dw+"기 적음","상대는 "+opp.workers+"기, 너는 "+workers+"기야. 초반 일꾼이 끊겼거나 병력에 과투자했다는 뜻 — 같은 시간 경제가 밀리면 물량·업글이 통째로 밀려. 일꾼은 잘려도 바로 다시 채우자.");
    else if(dw>=8) T("tip","vs","일꾼이 상대보다 "+dw+"기 적음","상대("+opp.workers+") 대비 경제가 조금 뒤졌어("+workers+"). 견제받는 중이 아니면 일꾼을 꾸준히 더 돌리자.");}
    var dup=((opp.atk_lv||0)+(opp.arm_lv||0))-(A+R);
    if(dup>=2) T("warn","vs","업그레이드가 상대보다 낮음","공"+A+"방"+R+" vs 상대 공"+(opp.atk_lv||0)+"방"+(opp.arm_lv||0)+". 풀업 화력전에서 두 단계 차이는 같은 병력도 한타에서 그냥 갈려 — 가스 남으면 업글부터 돌리자.");
    else if(dup===1) T("tip","vs","업글이 상대보다 한 단계 낮음","공"+A+"방"+R+" vs 공"+(opp.atk_lv||0)+"방"+(opp.arm_lv||0)+". 한 단계만 따라붙어도 교전 결과가 달라져.");
    if(!fast){var myNat=(p.townhalls&&p.townhalls.length>=2)?p.townhalls[1].t:null;
    if(myNat&&opp.nat){var de=_s2(myNat)-_s2(opp.nat);
      if(de>=90) T("tip","vs","앞마당이 상대보다 "+de+"초 늦음","앞마당 "+myNat+" vs 상대 "+opp.nat+". 압박이 없었다면 더 빨리 가져갔어야 — 확장이 늦으면 경제가 통째로 밀려서 이후 물량 차이로 벌어져.");}
    if((opp.tcount||0)-tc>=2) T("tip","vs","기지 수가 상대보다 적음","기지 "+tc+"개 vs 상대 "+opp.tcount+"개. 멀티 타이밍을 놓쳐 자원 격차가 벌어졌어 — 안전할 때 앞마당·삼룡이를 미리 가져가자.");}

    // 14. 매치업별 정밀 코칭 (레퍼런스 기반 — 매치업 특유의 타이밍·업글·조합)
    var mu=race+"v"+opp.race;
    function oHas(n){return !!(opp.uset&&opp.uset.has(n));}
    var myGate=build.filter(function(b){return b.name==="Gateway";}).length;
    var obs=(units["Observer"]||{}).n||0;
    var legZ=bnames.has("Leg Enhancements");
    var hasVes=!!units["Science Vessel"];
    var hasTankU=!!(units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"]);
    var late=(mins>=14)||(maxSup>=160);
    if(mu==="PvT"){
      if(!fast&&myGate>0&&opp.fact>0&&myGate<opp.fact+2) T("warn","mu","게이트웨이가 팩토리보다 적음","네 게이트 "+myGate+"개 vs 상대 팩토리 "+opp.fact+"개야. PvT는 '게이트 = 팩토리+2'가 기준이라, 그래야 큰 교전에서 병력과 충원을 감당해. 게이트를 더 늘리자.");
      if(obs<2&&mins>=8) T("tip","mu","옵저버가 부족 (PvT)","옵저버가 "+obs+"기뿐이야. PvT는 옵저버 2~3기로 스파이더 마인을 제거하고 시야를 잡아야 드라군이 안 녹아 — 항상 몇 기는 유지하자.");
      if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","질럿 발업(Leg)이 없음","발업 없는 질럿·드라군은 탱크/마인 조합을 못 버텨. 시타델 올려 발업부터 — 발업 질럿이 마인을 밟아주고 탱크 첫 볼리를 받아줘.");
      if(late&&!units["Arbiter"]&&!units["Carrier"]) T("warn","mu","후반 아비터/캐리어가 없음 (PvT)","지상 병력만으론 시즈 라인을 정면으로 못 넘어. 아비터 스테이시스로 탱크 덩어리를 얼리거나 리콜로 뒤를 치는 게 PvT 해법이야.");
    } else if(mu==="TvP"){
      if(!units["Vulture"]&&mins>=6) T("tip","mu","벌처가 안 보임 (TvP)","대프로토스 메카닉의 핵심은 벌처+마인이야. 벌처로 질럿을 견제하고 탱크를 질럿으로부터 가려줘 — 마인 라인으로 드라군도 묶고.");
      if((oHas("Carrier")||oHas("Arbiter"))&&!units["Goliath"]) T("warn","mu","상대 캐리어/아비터인데 골리앗이 없음","골리앗 없이는 캐리어·아비터에 대공이 비어. 골리앗을 섞고 사거리 업글로 공중을 받쳐야 해.");
    } else if(mu==="PvZ"){
      if(!units["Corsair"]&&!bnames.has("Photon Cannon")&&mins>=6) T("warn","mu","커세어가 없음 (PvZ)","커세어는 저글링 속업 이후 사실상 유일한 정찰 수단이고, 오버로드를 끊고 뭉친 뮤탈을 스플래시로 잡아. 커세어 없이는 정보와 제공권을 다 내줘 — 스타게이트+커세어를 챙기자.");
      if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","발업 질럿으로 맵 컨트롤 (PvZ)","발업 질럿은 저그 앞마당 압박과 맵 장악의 핵심이야. 커세어와 함께 발업 질럿을 굴리면 저그를 수세로 묶을 수 있어.");
    } else if(mu==="ZvP"){
      if(oHas("Corsair")&&!units["Scourge"]) T("tip","mu","상대 커세어엔 스컬지 (ZvP)","커세어가 오버로드와 뮤탈을 끊고 있어. 스컬지로 커세어를 줄여 오버로드(정찰·서플)를 지키는 게 ZvP 필수 대응이야.");
    } else if(mu==="TvZ"){
      if(hasVes&&hasTankU&&mxlv<1) T("tip","mu","베슬+탱크 타이밍엔 공1방1을 붙여라","첫 베슬+탱크로 나갈 때 인프 공1방1이 붙어야 디파일러 다크스웜 전에 이득을 봐. 업글 없이 나가면 손해만 보고 물러나게 돼.");
    } else if(mu==="ZvT"){
      if(!units["Lurker"]&&mins>=8) T("tip","mu","럴커 컨테인으로 지연 (ZvT)","럴커로 테란 앞마당·진출로를 막으면 마린메딕 타이밍을 늦춰 하이브까지 시간을 벌어. 뮤탈로 맵을 잡는 동안 럴커 라인을 깔자.");
    } else if(mu==="PvP"){
      if(obs<1&&mins>=6) T("warn","mu","옵저버 없이 PvP (다크/리버 위험)","PvP에서 옵저버가 없으면 다크템 드랍·리버 드랍을 못 보고 무너져. 옵저버 1~2기는 필수야.");
      if(!units["Reaver"]&&mins>=7) T("tip","mu","리버는 PvP의 핵심","리버는 확장 방어와 미네랄 견제의 핵심이고, 교전에선 최우선 타겟이야. 셔틀 리버로 상대 프로브를 지지면 경제 격차가 크게 벌어져.");
    } else if(mu==="TvT"){
      if(!hasTankU&&mins>=7) T("tip","mu","시즈 라인이 TvT의 전부","탱크 시즈 라인의 포지션이 TvT를 가른다. 하이그라운드 시즈와 마인 라인을 잡고, 드랍십으로 상대 멀티·일꾼을 흔들어 교착을 깨자.");
    } else if(mu==="ZvZ"){
      if(!units["Mutalisk"]&&mins>=5) T("warn","mu","ZvZ는 뮤탈+스컬지 싸움","뮤탈이 안 보여 — ZvZ는 뮤탈+스컬지 제공권이 곧 승패야. 스파이어를 놓치면 그대로 진다. 스택·클로닝·카라파이스 우위로 상대 뮤탈을 먼저 잡자.");
    }
  }

  // 15. 빠른무한(빨무) 전용 코칭 — 자원 무한이라 경제보다 물량·업글·조합이 승부
  if(fast){
    T("tip","fast","빨무는 경제가 아니라 물량·업글·조합 싸움","자원이 무한이라 일꾼·확장·정찰 관리는 거의 의미 없어. 돈이 남으면 "+prodKo+"부터 계속 늘리고, 남는 자원은 업글과 결정타 유닛으로 — '조합된 물량 + 끊김 없는 리맥스'가 빨무의 전부야.");
    if(workers>=26) T("tip","fast","일꾼이 너무 많음 (빨무)","빨무는 광맥이 본진에 붙어 있어 일꾼 "+workers+"기는 과해. 대략 12~20기면 충분하고 나머지 인구는 병력에 써야 물량이 더 나와 — 남는 일꾼은 인구 낭비야.");
    if(race==="P") T("tip","fast","프로토스는 빨무 최강 — 셔틀 드랍이 핵심","빨무는 토스가 유리해. 리버·질럿·아콘을 셔틀에 태워 상대 일꾼·본진을 순식간에 부수는 게 승리 공식이야. 하템 스톰도 덩어리 병력에 치명적 — 셔틀 견제를 축으로 굴리자.");
    else if(race==="T") T("tip","fast","테란은 메카닉을 넓게 펼쳐라 (빨무)","빨무 테란은 탱크+골리앗 메카닉이 축이야. 건물 완성 대기 탓에 초반 테크가 토스보다 느리니 조심하고, 교전 땐 병력을 넓게 펼쳐 사방에서 덮쳐 — 뭉치면 스톰·리버에 녹아.");
    else if(race==="Z") T("tip","fast","저그는 불리 — 성큰 버티고 가디언으로 (빨무)","빨무는 저그가 가장 불리해. 초반엔 성큰과 아군 백업으로 버티고 후반엔 히드라 웨이브+가디언으로 화력을 내되, 발키리에 취약하니 디바우러를 꼭 동반해. 하템·리버·베슬·탱크는 특히 조심.");
  }

  // 총평 (강점 + 1순위 개선 + 격려)
  var strong=[];
  if(prodN>=tgt) strong.push("생산기지");
  if(mxlv>=3) strong.push("풀업(공"+A+"방"+R+")"); else if(mxlv>=2) strong.push("업글");
  if(have_wt.length) strong.push("결정타 유닛");
  if(workers>=40) strong.push("경제");
  if(maxSup>=190&&have_wt.length) strong.push("조합된 물량");
  if(p.drops&&p.drops>=3) strong.push("견제");
  var hasTank2=units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"];
  var fixes=[];
  if(mxlv===0&&(haslv||up_n===0)) fixes.push("공·방 업그레이드");
  if(race==="P"&&!units["High Templar"]&&!units["Archon"]) fixes.push("하이템플러 스톰");
  if(race==="Z"&&mins>=12&&!hiveTech) fixes.push("하이브 전환(디파일러)");
  if(race==="T"&&mins>=8&&!hasTank2) fixes.push("시즈탱크");
  if(race==="T"&&marine>=12&&medic===0) fixes.push("메딕 추가");
  if(prodN<Math.max(2,tgt*0.6)) fixes.push(prodKo+" 수 늘리기");
  if(race==="Z"&&!units["Lurker"]&&!units["Defiler"]) fixes.push("럴커");
  if(maxSup>=190&&!have_wt.length&&!fixes.length) fixes.push("결정타 유닛 전환");
  if(mxlv>0&&mxlv<3&&!fixes.length) fixes.push("3업까지");
  var sstr=strong.length?strong.slice(0,3).join("·"):null;
  var verdict;
  if(!fixes.length) verdict=sstr?("이번 판은 군더더기 없이 탄탄해 — "+sstr+"까지 다 챙겼어. 이대로면 한타도 후반도 강해."):"무난하게 잘 풀어낸 한 판이야.";
  else if(fixes.length===1) verdict=(sstr?(sstr+"까진 잘 갖췄어. "):"")+"딱 하나, "+fixes[0]+"만 더 챙기면 한 단계 올라가.";
  else verdict=(sstr?("강점은 "+sstr+". "):"")+"개선 1순위는 "+fixes[0]+", 그다음 "+fixes[1]+" — 이 둘만 잡으면 확 달라져.";

  return [timings,pts,verdict];
}
function coach_report(a){
  var mins=(function(){var L=(a.meta&&a.meta.length)||"0:0";var q=(""+L).split(":");return ((+q[0])*60+(+q[1]||0))/60;})();
  const base=[];
  (a.players||[]).forEach(p=>{
    const unames=(p.units||[]).map(u=>u.name);
    const race=_coach_race(p.race,unames);const build=p.build||[];
    var units={};(p.units||[]).forEach(u=>units[u.name]=u);
    var workers=0,army=0;Object.keys(units).forEach(n=>{if(COACH_WORKERS.has(n))workers+=units[n].n;else army+=units[n].n*(COACH_SUPPLY[n]||1);});
    var th=p.townhalls||[];
    base.push({prod:build.filter(b=>COACH_PROD[race].has(b.name)).length,race:race,team:p.team,
      name:p.name,workers:workers,army:pyRound(army),atk_lv:p.atk_lv||0,arm_lv:p.arm_lv||0,
      tcount:th.length,nat:(th.length>=2?th[1].t:null),total_supply:p.total_supply||0,
      gate:build.filter(b=>b.name==='Gateway').length, fact:build.filter(b=>b.name==='Factory').length,
      uset:new Set(Object.keys(units).filter(n=>units[n].n>0))});
  });
  var fast=/(빨무|빠무|무한|fastest)/i.test((a.meta&&a.meta.map)||"");
  const out=[];
  (a.players||[]).forEach((p,i)=>{
    const peers=base.filter((b,j)=>j!==i);
    const r=coach_player(p,peers,mins,fast);
    out.push({id:p.id,name:p.name,race:p.race,timings:r[0],points:r[1],verdict:(fast?"[빠른무한 모드] ":"")+r[2]});
  });
  return out;
}
