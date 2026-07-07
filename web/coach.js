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
  var T=function(tone,k,ti,tx,sec){pts.push(sec!=null?{tone:tone,k:k,t:ti,x:tx,sec:sec}:{tone:tone,k:k,t:ti,x:tx});};
  var gas=_coach_first(build,COACH_GAS);
  var prodN=(p.main_prod_n!=null)?p.main_prod_n:build.filter(function(b){return COACH_PROD[race].has(b.name);}).length;
  var prodKo=p.main_prod_ko||({T:"배럭",P:"게이트",Z:"해처리"}[race]||"생산건물");
  var ups=build.filter(function(b){return b.cat==="upgrade"||b.cat==="tech";});var up_n=ups.length;var up1=ups.length?ups[0].t:null;var upsec=up1?_s2(up1):null;
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
    T("good","prod",prodKo+" "+prodN+"개 — 생산·리맥스 탄탄","권장 "+tgt+"개 이상 — 병력이 갈려도 바로 리맥스되는 구조야.");
  }else if(prodN<Math.max(2,tgt*0.6)){
    T("warn","prod",prodKo+" "+prodN+"개 — 생산기지 부족","기준 "+tgt+"개인데 "+prodN+"개 — 리맥스가 느려 한타 한 번에 무너져. 돈 남기 전에 "+prodKo+"부터.");
  }else{
    T("tip","prod",prodKo+" "+prodN+"개 — 조금 부족","권장 "+tgt+"개에 살짝 부족 — 2~3개만 더 지으면 리맥스가 확 빨라져.");
  }

  // 2. 업그레이드
  var usyn="";
  if(units["Goliath"]&&mxlv<2) usyn=" 골리앗은 공2업이 생명.";
  else if(units["Marine"]&&mxlv===0) usyn=" 마린은 공1업만 돼도 확 달라져.";
  else if(race==="Z"&&(units["Hydralisk"]||units["Zergling"])&&mxlv<2) usyn=" 다수 유닛엔 공업 한 단계가 곱으로 들어가.";
  if(haslv){
    var ut="업그레이드 공"+A+"·방"+R;
    if(mxlv===0)      T("warn","up",ut,"노업은 치명적 — 가스 오르면 공·방부터."+usyn,upsec);
    else if(mxlv<=1) T("tip","up",ut,"공·방 3업이 한타를 가른다 — 병력 뽑으며 꾸준히."+usyn,upsec);
    else if(mxlv>=3) T("good","up",ut,"3업 완성 — 업글 차이가 곧 한타 차이야.",upsec);
    else             T("good","up",ut,"꾸준했어 — 3업까지 마저 채우자.",upsec);
  }else if(up_n===0){
    T("warn","up","업그레이드 없음","물량전은 풀업 싸움 — 가스 오르면 업글부터.");
  }

  // 3. 종족별 결정타 (문서 금지사항 기반)
  if(race==="Z"){
    if(!units["Lurker"]&&!units["Defiler"]) T("tip","comp","러커가 없음","럴커 라인이 있어야 수세에서 벗어나 — 히드라 다음은 럴커.");
    var hiveTech=units["Defiler"]||units["Ultralisk"]||units["Guardian"];
    if(mins>=12&&!hiveTech) T("warn","comp","후반인데 하이브 카드가 없음","온리 히드라는 200 한타에서 녹아 — 하이브 올려 디파일러부터.");
    else if(mins>=9&&mins<12&&!hiveTech) T("tip","comp","하이브 전환 준비할 때","12분 전후 하이브 — 디파일러·가디언이 후반을 가른다.");
  }else if(race==="T"){
    var hasTank=units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"];
    if(mins>=8&&!hasTank) T("warn","comp","탱크 없이 바이오닉만","바이오닉만으론 라인을 못 뚫어 — 팩토리 2개+시즈탱크.");
    if(mins>=9&&!units["Science Vessel"]) T("tip","comp","베슬이 없음","베슬 2~3기가 스웜·클로킹·드랍 대응의 핵심이야.");
    if(marine>=12&&medic===0&&mins>=5) T("warn","comp","메딕 없이 마린만","마린 한 부대당 메딕 3~4기 — 없으면 럴커·스톰에 그냥 녹아.");
    else if(marine>=12&&enemyP>=2&&fbat===0) T("tip","comp","파벳이 없음 (상대 토스 "+enemyP+"명)","발업 질럿엔 파벳이 특효 — 부대에 3기만 섞자.");
  }else if(race==="P"){
    if(!units["High Templar"]&&!units["Archon"]) T(mins>=7?"warn":"tip","comp","하템(스톰)이 없음","질드라만으론 덩어리를 못 지워 — 스톰 한 방이 한타를 뒤집어.");
    if(units["Zealot"]&&!units["Dragoon"]) T("tip","comp","드라군 없이 질럿만","질럿만은 대공·사거리가 비어 — 드라군을 섞자.");
    if(p.drops!=null&&(p.drops||0)<1&&!(p.atk_first&&_s2(p.atk_first)<=360)&&mins>=8) T("tip","harass","견제가 적었음","토스의 힘은 견제 — 10분 전엔 한타보다 견제로 이득.");
  }
  if(have_wt.length) T("good","tech","결정타 확보: "+have_wt.join(", "),"후반은 게임체인저 유무로 갈려 — 좋은 판단.");

  // 4. 감지
  if(race==="P"&&!units["Observer"]&&!bnames.has("Photon Cannon")){
    T("warn","det","감지 수단 없음","다크·러커·마인을 못 보면 그냥 녹아 — 옵저버 1~2기 필수.");
  }else if(race==="T"&&!units["Science Vessel"]&&!bnames.has("Missile Turret")){
    T("tip","det","감지 수단 부족","다크·클로킹·드랍 대비 터렛/베슬을 챙기자.");
  }

  // 5. 멀티 (빨무에선 자원 무한이라 멀티 조언이 무의미 → 건너뜀)
  if(!fast&&race!=="Z"){
    if(tc>=2) T("good","exp","멀티 "+tc+"개 확보","생산처 분산 — 견제 복구도 물량도 빨라져.",(p.townhalls&&p.townhalls[1])?_s2(p.townhalls[1].t):null);
    else if(mins>=6) T("tip","exp","본진 하나 — 멀티 권장","본진 하나는 드랍 한 번에 휘청 — 멀티로 분산하자.");
  }

  // 6. 첫 200 / 물량
  if(maxSup>=190){
    if(have_wt.length) T("good","army","최대 ~"+Math.round(maxSup)+" 풀 병력","조합까지 갖춘 200 — 풀업 되면 바로 진출.");
    else T("tip","army","최대 ~"+Math.round(maxSup)+" — 조합은 아쉬움","빠른 200보다 조합된 200 — 결정타 유닛으로 전환하자.");
  }else if(mins>=9&&maxSup<130){
    T("tip","army","최대 ~"+Math.round(maxSup)+" — 물량 부족","물량이 얇아 — 생산기지를 늘려 자원을 병력으로.");
  }

  // 7. 일꾼 (빨무에선 일꾼 수 조언이 무의미 → 건너뜀; 빨무 전용 팁에서 따로)
  if(!fast){
  if(workers>=40) T("good","worker","일꾼 "+workers+"기 — 경제 탄탄","일꾼=돈=병력 — 경제 기반이 탄탄해.");
  else if(workers<22&&mins>=5) T("tip","worker","일꾼 "+workers+"기 — 부족","~50기까지 꾸준히 — 잘려도 바로 충원.");
  }

  // 8. APM
  if(series.length>=3){
    var body=series.length>3?series.slice(0,-1):series;
    var sorted=body.slice().sort(function(a,b){return a-b;});
    var med=body.length?sorted[Math.floor(body.length/2)]:0;
    var dip=[];body.forEach(function(v,i){if(med>0&&v<med*0.55)dip.push(i);});
    if(dip.length) T("tip","apm",dip[0]+"분에 손이 멈춤","평소("+med+") 절반 이하 — 교전 중에도 생산 단축키로 계속 찍자.",dip[0]*60);
  }
  if(apm&&eapm&&apm-eapm>=70){
    T("tip","apm","APM "+apm+" / 유효 "+eapm,"반복클릭이 많아 — 그 손을 생산·분배에 쓰자.");
  }

  // 9. 정찰 (빨무에선 정찰 타이밍이 무의미 → 건너뜀)
  if(!fast&&p.scouted!=null){
    if(p.scouted===0||!p.scout_first){
      T("tip","scout","정찰을 거의 안 함","정찰이 없으면 다크·올인을 모르고 당해 — 초반 한 번은 보자.");
    }else if(_s2(p.scout_first)<150){
      T("good","scout","초반 정찰 "+p.scout_first+(p.scouted>1?" ("+p.scouted+"곳)":""),"일찍 봤네 — 본 정보로 다음 수를 예측하자.",_s2(p.scout_first));
    }else if(_s2(p.scout_first)>240){
      var _std=race==="Z"?"오버로드 2기 직후":"첫 파일런/서플 직후";
      T("tip","scout","정찰이 늦음 "+p.scout_first,"표준은 "+_std+" — 늦으면 대응할 시간이 사라져.",_s2(p.scout_first));
    }
  }
  // 10. 컨트롤 그룹
  if(p.groups!=null&&p.groups<=2){
    T("tip","ctrl","컨트롤 그룹 "+p.groups+"개","그룹을 안 쓰면 교전 중 생산이 끊겨 — 병력/생산 분리 지정.");
  }else if(p.groups!=null&&p.groups>=6){
    T("good","ctrl","컨트롤 그룹 "+p.groups+"개","주력·생산·마법 분리 운용 — 상급 조작.");
  }
  // 11. 드랍 견제
  if(p.drops&&p.drops>=3){
    T("good","drop","드랍 견제 "+p.drops+"회","드랍으로 흔들었네 — 정면 압박과 병행하면 더 강해.");
  }
  // 12. 생산 연속성 (가동률/자원 소비율)
  if(p.prod_max_gap&&p.prod_max_gap>=90){
    T("tip","cont","생산 공백 최대 "+p.prod_max_gap+"초","생산이 끊긴 구간 = 돈 쌓임 신호 — 교전 중에도 계속 찍자.");
  }else if(p.prod_max_gap!=null&&p.prod_max_gap<=35&&(p.total_supply||0)>80){
    T("good","cont","생산 거의 안 끊김","공백 최대 "+p.prod_max_gap+"초 — 교전 중에도 계속 뽑은 최상급.");
  }

  // 13. 상대 비교 — 1v1은 정밀 비교, 팀전(2v2·3v3)은 상대팀 기준으로 발동
  var oppList=(peers||[]).filter(function(pe){return pe&&pe.team!=null&&p.team!=null&&pe.team!==p.team;});
  var oAny=function(n){return oppList.some(function(o){return o.uset&&o.uset.has(n);});};
  var vsT=oppList.some(function(o){return o.race==="T";}),vsP=oppList.some(function(o){return o.race==="P";}),vsZ=oppList.some(function(o){return o.race==="Z";});
  var obs=(units["Observer"]||{}).n||0;
  var legZ=bnames.has("Leg Enhancements");
  var hasVes=!!units["Science Vessel"];
  var hasTankU=!!(units["Siege Tank (Tank Mode)"]||units["Siege Tank (Siege Mode)"]);
  var late=(mins>=14)||(maxSup>=160);
  if(oppList.length){
    var is1=oppList.length===1;
    var best=oppList.reduce(function(a,b){return (((b.atk_lv||0)+(b.arm_lv||0))>((a.atk_lv||0)+(a.arm_lv||0)))?b:a;},oppList[0]);
    var who=is1?"상대":"상대팀 최고";
    var dup=((best.atk_lv||0)+(best.arm_lv||0))-(A+R);
    if(dup>=2) T("warn","vs","업그레이드가 "+who+"보다 낮음","공"+A+"방"+R+" vs 공"+(best.atk_lv||0)+"방"+(best.arm_lv||0)+" — 두 단계 차이는 한타가 그냥 갈려.",upsec);
    else if(dup===1) T("tip","vs","업글이 "+who+"보다 한 단계 낮음","공"+A+"방"+R+" vs 공"+(best.atk_lv||0)+"방"+(best.arm_lv||0)+". 한 단계만 따라붙어도 교전 결과가 달라져.",upsec);
    if(is1){
      var opp=oppList[0];
      if(!fast){var dw=(opp.workers||0)-workers;
      if(dw>=15) T("warn","vs","일꾼이 상대보다 "+dw+"기 적음","상대 "+opp.workers+" vs 나 "+workers+" — 경제가 밀리면 물량·업글이 통째로 밀려.");
      else if(dw>=8) T("tip","vs","일꾼이 상대보다 "+dw+"기 적음","상대("+opp.workers+") 대비 경제가 조금 뒤졌어("+workers+"). 견제받는 중이 아니면 일꾼을 꾸준히 더 돌리자.");}
      if(!fast){var myNat=(p.townhalls&&p.townhalls.length>=2)?p.townhalls[1].t:null;
      if(myNat&&opp.nat){var de=_s2(myNat)-_s2(opp.nat);
        if(de>=90) T("tip","vs","앞마당이 상대보다 "+de+"초 늦음","앞마당 "+myNat+" vs "+opp.nat+" — 확장이 늦으면 경제가 통째로 밀려.",_s2(myNat));}
      if((opp.tcount||0)-tc>=2) T("tip","vs","기지 수가 상대보다 적음","기지 "+tc+" vs "+opp.tcount+" — 안전할 때 미리 가져가자.");}
    }

    // 14. 매치업 코칭 — 상대팀에 해당 종족·유닛이 있으면 발동 (팀전 포함)
    if(race==="T"&&(oAny("Carrier")||oAny("Arbiter"))&&!units["Goliath"]) T("warn","mu","상대 캐리어/아비터인데 골리앗이 없음","골리앗+사거리업으로 공중을 받쳐야 해.");
    if(race==="Z"&&oAny("Corsair")&&!units["Scourge"]) T("tip","mu","상대 커세어엔 스컬지","스컬지로 커세어를 줄여 오버로드를 지키자.");
    if(!fast){
      var myGate=build.filter(function(b){return b.name==="Gateway";}).length;
      if(race==="P"&&vsT){
        if(is1&&myGate>0&&oppList[0].fact>0&&myGate<oppList[0].fact+2) T("warn","mu","게이트웨이가 팩토리보다 적음","게이트 "+myGate+" vs 팩 "+oppList[0].fact+" — 기준은 팩토리+2.");
        if(obs<2&&mins>=8) T("tip","mu","옵저버가 부족 (PvT)","옵저버 2~3기로 마인 제거 — 드라군이 안 녹아.");
        if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","질럿 발업(Leg)이 없음","발업 질럿이 마인을 밟고 탱크 볼리를 받아줘 — 시타델부터.");
        if(late&&!units["Arbiter"]&&!units["Carrier"]) T("warn","mu","후반 아비터/캐리어가 없음 (PvT)","시즈 라인은 아비터(스테이시스·리콜)로 푼다.");
      }
      if(race==="T"&&vsP&&!units["Vulture"]&&mins>=6) T("tip","mu","벌처가 안 보임 (TvP)","벌처+마인이 질럿을 막고 드라군을 묶어.");
      if(race==="P"&&vsZ){
        if(!units["Corsair"]&&!bnames.has("Photon Cannon")&&mins>=6) T("warn","mu","커세어가 없음 (PvZ)","커세어가 정찰·제공권의 전부 — 스타게이트부터.");
        if(units["Zealot"]&&!legZ&&mins>=8) T("tip","mu","발업 질럿으로 맵 컨트롤 (PvZ)","커세어+발업 질럿으로 저그를 수세로 묶자.");
      }
      if(race==="T"&&vsZ&&hasVes&&hasTankU&&mxlv<1) T("tip","mu","베슬+탱크 타이밍엔 공1방1을 붙여라","첫 진출엔 공1방1 — 노업 진출은 손해만 봐.");
      if(race==="Z"&&vsT&&!units["Lurker"]&&mins>=8) T("tip","mu","럴커 컨테인으로 지연 (ZvT)","럴커로 진출로를 막아 하이브까지 시간을 벌자.");
      if(race==="P"&&vsP){
        if(obs<1&&mins>=6) T("warn","mu","옵저버 없이 PvP (다크/리버 위험)","다크·리버 드랍을 못 보면 무너져 — 옵저버 필수.");
        if(!units["Reaver"]&&mins>=7) T("tip","mu","리버는 PvP의 핵심","셔틀 리버로 프로브를 지지면 경제가 벌어져.");
      }
      if(race==="T"&&vsT&&!hasTankU&&mins>=7) T("tip","mu","시즈 라인이 TvT의 전부","시즈 포지션이 전부 — 드랍십으로 교착을 깨자.");
      if(race==="Z"&&vsZ&&!units["Mutalisk"]&&mins>=5) T("warn","mu","ZvZ는 뮤탈+스컬지 싸움","뮤탈+스컬지 제공권이 승패 — 스파이어부터.");
    }
  }

  // 15. 빠른무한(빨무) 전용 — 매판 같은 문구를 반복하지 않고, 조건이 걸릴 때만
  if(fast){
    if(prodN<tgt||mxlv<2) T("tip","fast","빨무 핵심: 물량·업글·조합","남는 돈은 "+prodKo+"·업글·결정타로 — 조합된 물량이 전부야.");
    if(workers>=26) T("tip","fast","일꾼이 너무 많음 (빨무)","12~20기면 충분 — 남는 인구는 병력으로.");
    if(race==="P"&&mins>=8){
      if(!units["Shuttle"]&&!units["Reaver"]) T("tip","fast","셔틀 견제가 없음 (빨무)","셔틀 리버가 승리 공식 — 로보틱스부터.");
      else if(p.drops&&p.drops>=2) T("good","fast","셔틀 견제 운용 (빨무)","빨무 토스의 승리 공식 — 정면과 병행하면 더 강해.");
    }
    if(race==="T"&&mins>=8&&!(hasTankU&&units["Goliath"])) T("tip","fast","탱크+골리앗 축이 아직 (빨무)","넓게 펼친 탱크+골리앗으로 센터를 가르자.");
    if(race==="Z"&&oAny("Valkyrie")&&!units["Devourer"]) T("warn","fast","상대 발키리엔 디바우러 (빨무)","디바우러로 발키리를 걷어내야 화력이 살아.");
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

  // 5축 등급 (S/A/B/C) — 리포트 상단 요약용
  var coreOK=race==="T"?!!hasTank2:(race==="P"?!!(units["High Templar"]||units["Archon"]):!!(units["Lurker"]||hiveTech));
  var g_cont=(p.prod_max_gap==null)?null:(p.prod_max_gap<=35?"S":p.prod_max_gap<=60?"A":p.prod_max_gap<=90?"B":"C");
  var g_har=(p.drops==null&&!p.atk_first)?null:((p.drops||0)>=3?"S":(p.drops||0)>=1?"A":(p.atk_first&&_s2(p.atk_first)<=420?"B":"C"));
  var grades=[
    {k:"생산",g:prodN>=tgt+2?"S":prodN>=tgt?"A":prodN>=Math.max(2,tgt*0.6)?"B":"C"},
    {k:"업글",g:(!haslv&&up_n===0)?"C":(mxlv>=3?"S":mxlv===2?"A":mxlv===1?"B":"C")},
    {k:"조합",g:have_wt.length>=2?"S":(have_wt.length?"A":(coreOK?"B":"C"))},
    {k:"가동률",g:g_cont},
    {k:"견제",g:g_har}
  ].filter(function(x){return x.g;});

  return [timings,pts,verdict,grades];
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
    out.push({id:p.id,name:p.name,race:p.race,timings:r[0],points:r[1],verdict:(fast?"[빠른무한 모드] ":"")+r[2],grades:r[3]||[]});
  });
  return out;
}
