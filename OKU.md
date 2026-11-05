# Keep on Mining Bot

## Kurulum
1. `kur.bat` dosyasına çift tıkla (bir kere yeterli).

## Kullanım
1. Oyunu **pencere modunda** aç (1920x1080 veya 2560x1440).
2. Bir madene gir.
3. `baslat.bat` dosyasını çalıştır.
4. Oyuna tıkla ve **F8** ile başlat/duraklat. **F9** ile tamamen kapat.
5. Acil durumda fareyi ekranın **sol üst köşesine** götür, bot duraklar.

## Kontrol paneli
`baslat.bat` çalıştırınca tarayıcıda **http://127.0.0.1:8770** açılır (sadece bu bilgisayardan erişilir).
- **Genel:** bot durumu, Başlat/Duraklat, dünya/level/kazma, cüzdan, birikim hedefleri (ilerleme çubuklu), son kararlar.
- **İstatistik ve getiri:** oturum başına grafik (kaya, XP, her kaynak), ilk yarı / son yarı karşılaştırması
  (botun yatırımları kazancı ne kadar artırdı), kaynak başına toplam kazanç/harcama/net, modül bazlı harcamalar.
- **Ayarlar:** ayarlar.toml formdan düzenlenir, yorumlar korunur, bot yeni ayarı hemen kullanır. Ham düzenleyici de var.
- **Günlük:** altta ince çubuk; tıklayınca açılır. Her kararın yanında "neden?" ile gerekçesi (puan, alternatifler,
  birikim yüzünden bekleyenler, formül).
- Kayıtlar `kayitlar/` klasöründe: `istatistik.json` (kalıcı), `olaylar.jsonl` (tüm günlük).
- Eski konsol modu: `python main.py --konsol`. Bot açılınca kendiliğinden başlasın: `[panel] otomatik_baslat = true`.

## Otomatik açılış
`baslat.bat` oyun kapalıysa önce en yeni köprü eklentisini kurar, sonra oyunu Steam üzerinden açar,
ana menüde "Oyna!"ya basar. Ardından F8 ile kazmayı başlatırsın. Süre bitince bot "MADENE GİT!"e kendisi basar.

## Kazma önceliği
Puan = 100 / oyundaki çıkma şansı. En nadir mücevher/cevher önce kazılır, eser taşıyan kaya her zaman en öndedir.
Şanslar her madende oyundan yeniden okunur, yani yetenek ağacından şans yükselttikçe sıralama kendiliğinden güncellenir.

## Mod modu (önerilen)
Oyuna BepInEx ve `mod/KomKopru.dll` köprü eklentisi kurulu. Oyun açıkken bot kayaların
türünü, konumunu ve eser taşıyıp taşımadığını doğrudan oyundan okur. Renk tanıma kullanmaz.
`baslat.bat` köprüyü otomatik bulur; bulamazsa ekran okumaya geçer.
- Eklentiyi değiştirdikten sonra: `mod\derle.bat` dosyasını çalıştır ve oyunu yeniden başlat.
- Oyunu canlı incelemek için: `python kesif.py durum` veya `python kesif.py alanlar TheAnvil`.
- Modu kaldırmak için: Steam → oyuna sağ tık → Özellikler → Yüklü Dosyalar → Dosya bütünlüğünü doğrula.
  (Bu sadece oyunun kendi dosyalarını onarır. Tamamen silmek için oyun klasöründeki `BepInEx`,
  `winhttp.dll`, `doorstop_config.ini` ve `.doorstop_version` dosyalarını sil.)
- Kayıt dosyası yedeği `yedek/` klasöründe.

## Test modu (fare oynamaz)
Madendeyken bir komut penceresinde:

    python main.py --test

`debug/tespit.png` dosyasında botun gördüğü cevherler işaretli olur.
Yanlış ya da eksik bir şey varsa bu dosyayı bana at.

## Ayarlar (`ayarlar.toml`)
- `[kazma] tahta`: Kazılacak alan (pencereye göre oransal).
- `[[cevher]]`: Her cevher türünün rengi ve öncelik puanı. Puanı yüksek olan önce kazılır.
- `[ihtiyac] hedef`: Belirli bir kaynak lazımsa sınıf adını yaz, örn. `"gumus_beyaz"`.

## Dünya değişince arka plan
Bot zemini sabit bir renk olarak tanımlamaz. Her madene girişte tahtada en çok yer kaplayan
renkleri (zemin ve sıradan kayalar) otomatik öğrenip cevher aramasından çıkarır.
Bu yüzden kar, taş ya da çim zeminde ekstra ayar gerekmez.

## Oturum arası döngü (planlayıcı)
Süre bitince açılır pencereler kapatılır, sonra planlayıcı (`bot/planlayici.py`) karar verir:
- Örs ve yetenek ağacı adaylarını TEK bütçede karşılaştırır. Puan = değer × (cüzdan / maliyet).
- Birikim: bir kaynakta henüz alınamayan önemli bir hedef varsa (örn. MoreTime5, kazma #8),
  o kaynaktan sadece cüzdanın %10'undan ucuz şeyler alınır.
- Dünyalar: mor kitap yetince yeni dünya açar ve en iyi 2 kartı seçer; kırmızı kitapla kart yükseltir;
  en verimli dünyayı seçer (verim, oturum sonuçlarından öğrenilen vuruş kapasitesiyle hesaplanır).
- Otomatik madenler: satın alma + hız/miktar yükseltmeleri aynı bütçede yarışır. Değer = maden ağırlığı ×
  üretim artışı (miktar: 1/adet; hız: her alımda gerçek süre düşüşünden öğrenilir, ~%4).
  XP madeni mor kitap istediği için kendiliğinden alınmaz.
- Paylaşılan güçlendirmeler (SharedBuffs kartı): kuşanılı olmayan kazmalardan ağırlığı en yüksek olanlar
  otomatik seçilir (`[ors.paylasilan.agirliklar]`, kazma numarasına göre).
- Başarısız bir işlem turu bitirmez; o işlem 10 tur atlanır. Geliri olmayan kaynağa bağlı hedefler
  (örn. henüz açılmamış viridyum) "ulaşılamaz" sayılır ve hiçbir kaynağı kilitlemez.
- Menüye ve sekmelere SADECE yapılacak bir iş varsa girilir; yoksa bot doğrudan MADENE GİT!'e basar.

## Yol haritası
- [x] Maden kazma (nadirlik sırası, gruplama, sanal imleç)
- [x] Madenden çıkış / yeniden giriş döngüsü, açılır pencere kapatma
- [x] Örs: kazma yapma, kuşanma, seviye atlatma
- [x] Yetenek ağacı: en verimli düğümü alma (önbellekli)
- [ ] Madenler (otomatik farm) yükseltmeleri
- [ ] Dünya açma ve yetenek seçimi
