# 920-as tesztjavítás: páratlan szélességű YUV→BGRA képkonverzió

A `vero5-920-olympia-image-odd-width-conversion.patch` célzott tesztkerülőút
a Kodi 21.3 / FFmpeg 6.0.1 képkonverziójához. A 919-es diagnosztika megmarad.
Nem upstream javítás backportja, és az alkalmazhatósági ellenőrzés nem bizonyítja
a készülékes hibajavítást.

## Bizonyíték és hipotézis

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

## Készülékes ellenőrzés a felhasználó által végzett build/telepítés után

1. Őrizd meg a régi mérési archívumot. Azonos Moonraker cache-fájllal mérj;
   az első tesztben ne ürítsd vagy generáld újra a cache-t.
2. A csomag és a telepített `kodi.bin` hash-egyezését a bevált eljárással ellenőrizd.
   A buildnaplóban a saját `vero5-9…` patchek száma ekkor 20, az utolsó a 920-as.
3. A diagnosztikai config maradjon az alábbi célképre állítva, majd a telepítés
   után új Kodi-folyamatban kezdj mérést:
   `/home/osmc/.kodi/userdata/Thumbnails/1/14dc1e2d.jpg`.
   A régi hash `7f74f41d1b15412f558bcace5732f9950b9a7977959c860693044b20814fecc9`.
4. A friss `texture-edge-diag-*` mappát használd. Böngéssz ki-be legalább öt új
   betöltésig, és figyeld, visszatér-e a jobb szélső hiba. Az új betöltést a `begin`
   ID-k igazolják, nem a kijelölések száma. Rögzíts képernyőmentést és időpontot.
5. Az új mentések között a valódi kép utolsó oszlopa is legyen stabil; a padding
   a kitöltés után legyen helyes. Az `analyze.py` a teljes képtartomány hashét
   vizsgálja, az alfaadatokkal együtt. A `decoded` paddingterületének eltérése
   önmagában továbbra sem hibajel.
6. Ha a vizuális hiba és az utolsó oszlop véletlen eltérése is megszűnik, az
   alátámasztja a hipotézist. Ha nem, az új mentésekkel folytatjuk a vizsgálatot;
   ne nevezzük a tesztet igazolt javításnak.

A guard aktiválódásáról debug naplószinten ez a sor készül:
`CFFmpegImage: odd-width unscaled YUV conversion bypass, ...`.
Normál naplószinten a hiánya nem bizonyítja, hogy a guard nem futott le.
A 919-es mentéskorlátok és a naplókorlátok továbbra is érvényesek.

Kontrollként nézz meg páros szélességű posztereket és más GUI-képeket is.
Az új build előtt és után a Kodi többi alapfunkciójának működését a készüléken
szükséges ellenőrizni. A készítéskor buildet, telepítést, commitot és push-t
az agent nem végez.
