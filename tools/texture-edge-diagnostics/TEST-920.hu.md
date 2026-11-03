# 920-as javítás: páratlan szélességű YUV→BGRA képkonverzió

A `vero5-920-olympia-image-odd-width-conversion.patch` célzott Kodi oldali
kerülőmegoldás a Kodi 21.3 / FFmpeg 6.0.1 képkonverziójához. Az
`21.3.0-12+olympia3` kiadásból a 919-es diagnosztikai patch-et eltávolítottuk,
a javítás független attól. Nem upstream FFmpeg-javítás backportja.
Az FFmpeg frissítésekor a kerülőút szükségességét újra kell értékelni.

## Forrásvizsgálat és megőrzött bizonyíték

A Vero V-on a Moonraker kép 379×540, a textúra 384×540 volt. A biztosan hibás
3-as és a biztosan jó 4-es betöltés között kizárólag a valódi kép 378-as oszlopa
változott, mind az 540 sorban. Az 5 kitöltési oszlop ezt pontosan követte.
Az eltérés a dekódolás utáni mentésben már jelen volt, és az adott betöltés
`decoded`, `clamped`, `upload` mentései bájtra egyeztek. A cache-fájl változatlan.

A mentett bizonyíték: `moonraker-edge-bad3-good4.tar.gz`, SHA256:

```text
aefd0546c713b3f85899fa5f260d951c612b3199c742cd5d4f704363e55a6d9e
```

A build VM-en megvizsgált FFmpeg 6.0.1-ben a generikus `yuv2rgb_c_32` útvonal
8/4/2 pixelblokkokat ír, a megmaradó egyetlen pixelt nem. A kiválasztás páros
magasságot igényel, de nem zárja ki a páratlan szélességet. A külön ARM NEON
unscaled útvonal 16-tal osztható szélességet igényel, így 379-nél nem választható.
A ténylegesen futó konverziós függvényt az első mérés nem azonosította közvetlenül.

## A módosítás határa

Csak a Kodi `CFFmpegImage::DecodeFrame()` konverziójának alábbi esete változik:

- páratlan célképszélesség és páros célképmagasság;
- a célméret pontosan megegyezik az eredeti képmérettel;
- a normalizált forrásformátum YUV420P, YUV422P vagy YUVA420P.

Ekkor a `SWS_BICUBIC` mellé `SWS_ACCURATE_RND` kerül. A megvizsgált FFmpeg
kiválasztási feltétele szerint ez kizárja a gyanús unscaled gyorsutat.
A JPEG YUVJ420P/YUVJ422P formátumait a Kodi már ezekre normalizálja;
a meglévő teljes színtartomány-kezelés megmarad.

A kép mérete, a cache-fájl és a padding kódja nem változik; a teszt nem
nullázással vagy az utolsó oszlop levágásával rejti el az eltérést.
A videolejátszó útvonalát és a processz globális CPU-feature beállítását nem érinti.
A kerekítési mód és a választott konverziós út megváltozhat, ezért a korábbi build
képadatával nem követelünk bájtra egyezést; az érintett képeknél teljesítményváltozás
is lehetséges. A többi képkonverzió az eredeti flageket használja.

## A 920-as tesztbuild eredménye

A felhasználó a `f3bceba92` commitot lefordította és Vero V-ra telepítette.
A telepített és a csomagból kiolvasott `kodi.bin` SHA256-értéke egyezett:
`958ca0f2590a776e181f424c44d20fb7362b4ef94514c68fa2e511c2ff8bb9e6`.

A cache-kép változatlan maradt:
`/home/osmc/.kodi/userdata/Thumbnails/1/14dc1e2d.jpg`, SHA256:
`7f74f41d1b15412f558bcace5732f9950b9a7977959c860693044b20814fecc9`.

Az új mérési mappa `texture-edge-diag-1msdU5` volt. Nyolc külön betöltésnél
nem jelentkezett a vizuális hiba. Mind a nyolc teljes feltöltési puffer hash-e:
`91b728b679a0ab100141fe7cb6c40a2952743267a1f495a1046114f2bda471c6`.
Mindegyik BGRA, 379×540 képméretű volt, a jobb és alsó kitöltés hibaszáma 0.
Ez az adott képen alátámasztja a kerülőmegoldás hatásosságát; nem igazolja
önmagában az összes képformátum vagy készülék működését.

## Olympia3 véglegesítés

- A 919-es patch kikerült a build könyvtárából. A teljes Kodi-forrás friss
  kibontásakor így nem kerül bele diagnosztikai mező, mérési pont, segédkód,
  CMake-bejegyzés vagy puffermentés.
- A 920-as fájlnév és a bevizsgált feltétel megmaradt; a külön teszt-debugsort
  eltávolítottuk. A konverziós flagek logikája változatlan a sikeres teszthez képest.
- A csomagverzió `21.3.0-12+olympia3`. A debug csomag verzióját és azonos verziójú
  főcsomagra mutató függőségét a buildscript a főcsomag vezérlőfájljából generálja.
- A számozásban a 919 helye üres marad. A saját `vero5-9…` patchek száma 19,
  a teljes `all/arm/vero5` sor 81 patch.
- A `README.hu.md`, `analyze.py` és `test_analyze.py` történeti mérőeszközök;
  nincsenek beépítve az új Kodiba. A 919-es patch korábbi Git-commitból előkereshető.

## Végső készülékes ellenőrzés

A commitot, push-t, buildet és telepítést a felhasználó végzi.

1. A VM-en ellenőrizd a végleges commitot, a 920-as patch új hashét és a
   `Version: 21.3.0-12+olympia3` sort. A 919-es patch ne legyen a patchkönyvtárban.
2. Sikeres build után a naplóban 19 saját patch legyen, az utolsó a 920-as;
   a 919-es ne szerepeljen alkalmazott patchként. A csomagverzió legyen olympia3.
3. A bevált eljárással ellenőrizd az átmásolt csomag hashét és a telepített
   `kodi.bin` egyezését a csomagban levővel.
4. Az eredeti cache-kép megtartásával, normál böngészés közben ellenőrizd a
   Moonrakert és más, korábban hibás posztereket. Próbálj páros szélességű
   kontrollképeket is, és figyeld, változik-e a böngészés sebessége.
5. Az olympia3 már nem olvassa a `texture-edge-diagnostics.conf` fájlt, és nem
   hoz létre új mérési mappát. A régi config, archívumok és mérési mappák a
   készüléken megmaradnak; a csomag nem törli őket.

A diagnosztika nélküli végleges build fordítása és készülékes próbája a helyi
patchalkalmazási ellenőrzésből nem következik; ez külön, még elvégzendő lépés.
