// Keep on Mining Bot - köprü eklentisi (BepInEx 5)
// Oyunun durumunu 127.0.0.1:8765 üzerinden JSON olarak verir ve komutları ana iş parçacığında uygular.
// Sadece yerel makineden erişilebilir. C# 5 ile derlenir (csc.exe v4).
//
// Uç noktalar:
//   /ping                              -> "ok"
//   /durum                             -> ekran boyutu, maden oturumu, kayalar (ekran koordinatıyla)
//   /alanlar?sinif=TheAnvil            -> o sınıfın ilk örneğinin tüm alan değerleri
//   /metotlar?sinif=TheAnvil           -> metot imzaları
//   /cagir?sinif=X&metot=Y&a=1&a=foo   -> metodu çağırır (argümanlar parametre tipine çevrilir)
//   /ayarla?sinif=X&alan=Y&deger=Z     -> bir alanın değerini değiştirir (sadece hata ayıklama için)
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;
using BepInEx;
using UnityEngine;

namespace KomBot
{
    [BepInPlugin("kombot.kopru", "KoM Bot Kopru", "0.1.0")]
    public class KomKopru : BaseUnityPlugin
    {
        const BindingFlags BF = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
        static readonly CultureInfo INV = CultureInfo.InvariantCulture;

        HttpListener dinleyici;
        Thread dinleThread;
        readonly Queue<Is> kuyruk = new Queue<Is>();
        Assembly oyunAsm;

        class Is
        {
            public Func<string> Gorev;
            public string Sonuc;
            public ManualResetEvent Bitti = new ManualResetEvent(false);
        }

        // ---- sanal imleç: kazma dairesini gerçek fare yerine bot yönetir ----
        volatile bool sanalAktif;
        float sanalX, sanalY; // ekran pikseli, sol üst köşe orijinli
        Type circleFollowTip, circle2DTip;

        long sonImlecTik; // son imleç komutunun zamanı (UTC tick) - iş parçacığından güvenli

        void LateUpdate()
        {
            // Güvenlik: bot 3 sn komut göndermezse (çöktü/kapandı) daire gerçek fareye döner
            if (sanalAktif && (DateTime.UtcNow.Ticks - Interlocked.Read(ref sonImlecTik)) > TimeSpan.TicksPerSecond * 3)
                sanalAktif = false;
            if (!sanalAktif || circleFollowTip == null) return;
            Camera cam = Camera.main;
            if (cam == null) return;
            Vector3 w = cam.ScreenToWorldPoint(new Vector3(sanalX, Screen.height - sanalY, cam.nearClipPlane));
            w.z = 1f;
            foreach (UnityEngine.Object o in UnityEngine.Object.FindObjectsOfType(circleFollowTip))
                ((Component)o).transform.position = w;
        }

        string Imlec(string x, string y, string birak)
        {
            if (birak == "1") { sanalAktif = false; return "{\"tamam\":true,\"sanal\":false}"; }
            Interlocked.Exchange(ref sonImlecTik, DateTime.UtcNow.Ticks);
            sanalX = float.Parse(x, INV);
            sanalY = float.Parse(y, INV);
            sanalAktif = true;
            return "{\"tamam\":true,\"sanal\":true}";
        }

        // Kazma dairesinin ekrandaki merkezi ve yarıçapı (piksel)
        string CemberBilgisi()
        {
            Camera cam = Camera.main;
            if (cam == null || circleFollowTip == null) return "null";
            UnityEngine.Object[] hepsi = UnityEngine.Object.FindObjectsOfType(circleFollowTip);
            if (hepsi.Length == 0) return "null";
            Component c = (Component)hepsi[0];
            Vector3 m = cam.WorldToScreenPoint(c.transform.position);
            float rpx = -1f;
            if (circle2DTip != null)
            {
                Component col = c.GetComponentInChildren(circle2DTip, true);
                if (col != null)
                {
                    float r = (float)circle2DTip.GetProperty("radius").GetValue(col, null);
                    Vector3 s = col.transform.lossyScale;
                    float wr = r * Mathf.Max(Mathf.Abs(s.x), Mathf.Abs(s.y));
                    Vector3 kenar = cam.WorldToScreenPoint(col.transform.position + new Vector3(wr, 0f, 0f));
                    Vector3 merkez = cam.WorldToScreenPoint(col.transform.position);
                    rpx = Mathf.Abs(kenar.x - merkez.x);
                }
            }
            return "{\"x\":" + m.x.ToString("0.0", INV) + ",\"y\":" + (Screen.height - m.y).ToString("0.0", INV)
                 + ",\"r\":" + rpx.ToString("0.0", INV) + ",\"sanal\":" + (sanalAktif ? "true" : "false") + "}";
        }

        void Awake()
        {
            Application.runInBackground = true; // oyun arka plandayken de çalışsın
            foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
                if (a.GetName().Name == "Assembly-CSharp") oyunAsm = a;
            if (oyunAsm != null) circleFollowTip = oyunAsm.GetType("CircleFollow");
            circle2DTip = TumTip("UnityEngine.CircleCollider2D");
            try
            {
                dinleyici = new HttpListener();
                dinleyici.Prefixes.Add("http://127.0.0.1:8765/");
                dinleyici.Start();
                dinleThread = new Thread(Dinle);
                dinleThread.IsBackground = true;
                dinleThread.Start();
                Logger.LogInfo("KoM Bot köprüsü 127.0.0.1:8765 üzerinde çalışıyor");
            }
            catch (Exception e) { Logger.LogError("Köprü başlatılamadı: " + e); }
        }

        void OnDestroy()
        {
            try { if (dinleyici != null) dinleyici.Stop(); } catch { }
        }

        // ---------------- HTTP ----------------
        void Dinle()
        {
            while (dinleyici != null && dinleyici.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = dinleyici.GetContext(); } catch { return; }
                string cevap;
                int kod = 200;
                try { cevap = Isle(ctx.Request); }
                catch (Exception e) { kod = 500; cevap = "{\"hata\":" + Js(e.ToString()) + "}"; }
                try
                {
                    byte[] b = Encoding.UTF8.GetBytes(cevap);
                    ctx.Response.StatusCode = kod;
                    ctx.Response.ContentType = "application/json; charset=utf-8";
                    ctx.Response.ContentLength64 = b.Length;
                    ctx.Response.OutputStream.Write(b, 0, b.Length);
                    ctx.Response.OutputStream.Close();
                }
                catch { }
            }
        }

        string Isle(HttpListenerRequest r)
        {
            string yol = r.Url.AbsolutePath.Trim('/');
            var q = r.QueryString;
            switch (yol)
            {
                case "ping": return "\"ok\"";
                case "durum": return AnaIsParcacigi(Durum);
                case "alanlar": { string s = q["sinif"]; return AnaIsParcacigi(delegate { return Alanlar(s); }); }
                case "metotlar": { string s = q["sinif"]; return AnaIsParcacigi(delegate { return Metotlar(s); }); }
                case "cagir":
                    {
                        string s = q["sinif"], m = q["metot"];
                        string[] args = q.GetValues("a") ?? new string[0];
                        return AnaIsParcacigi(delegate { return Cagir(s, m, args); });
                    }
                case "imlec":
                    {
                        string x = q["x"], y = q["y"], b = q["birak"];
                        return Imlec(x, y, b); // sadece alan yazar, ana iş parçacığı gerekmez
                    }
                case "bilesenler":
                    {
                        string o = q["onek"], t = q["tip"];
                        return AnaIsParcacigi(delegate { return Bilesenler(o, t); });
                    }
                case "uzerine_gel":
                    {
                        string a = q["ad"], c = q["cik"];
                        return AnaIsParcacigi(delegate { return UzerineGel(a, c == "1"); });
                    }
                case "metinler": { string a = q["ad"]; return AnaIsParcacigi(delegate { return Metinler(a); }); }
                case "butonlar": return AnaIsParcacigi(delegate { return Butonlar(null); });
                case "bas": { string m = q["metin"]; return AnaIsParcacigi(delegate { return Butonlar(m); }); }
                case "ayarla":
                    {
                        string s = q["sinif"], a = q["alan"], d = q["deger"];
                        return AnaIsParcacigi(delegate { return Ayarla(s, a, d); });
                    }
            }
            return "{\"hata\":\"bilinmeyen yol\"}";
        }

        string AnaIsParcacigi(Func<string> f)
        {
            var i = new Is { Gorev = f };
            lock (kuyruk) kuyruk.Enqueue(i);
            if (!i.Bitti.WaitOne(3000)) return "{\"hata\":\"zaman asimi (oyun duraklatilmis olabilir)\"}";
            return i.Sonuc;
        }

        void Update()
        {
            while (true)
            {
                Is i;
                lock (kuyruk) { if (kuyruk.Count == 0) return; i = kuyruk.Dequeue(); }
                try { i.Sonuc = i.Gorev(); }
                catch (Exception e) { i.Sonuc = "{\"hata\":" + Js((e.InnerException ?? e).ToString()) + "}"; }
                i.Bitti.Set();
            }
        }

        // ---------------- yardımcılar ----------------
        Type Tip(string ad)
        {
            Type t = oyunAsm != null ? oyunAsm.GetType(ad) : null;
            if (t == null) throw new Exception("sinif bulunamadi: " + ad);
            return t;
        }

        UnityEngine.Object Ornek(Type t)
        {
            // Pasif objeler dahil ara (menü sekmeleri kapalıyken de bulunsun)
            UnityEngine.Object[] hepsi = Resources.FindObjectsOfTypeAll(t);
            UnityEngine.Object yedek = null;
            foreach (UnityEngine.Object o in hepsi)
            {
                Component c = o as Component;
                if (c == null || !c.gameObject.scene.IsValid()) continue; // prefab'ları atla
                if (c.gameObject.activeInHierarchy) return o;
                if (yedek == null) yedek = o;
            }
            return yedek;
        }

        static string Js(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 32) sb.Append("\\u" + ((int)c).ToString("x4")); else sb.Append(c);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }

        static string Deger(object v, int derinlik)
        {
            if (v == null) return "null";
            if (v is bool) return ((bool)v) ? "true" : "false";
            if (v is float) { float f = (float)v; return (float.IsNaN(f) || float.IsInfinity(f)) ? "null" : f.ToString("R", INV); }
            if (v is double) { double d = (double)v; return (double.IsNaN(d) || double.IsInfinity(d)) ? "null" : d.ToString("R", INV); }
            if (v is int || v is long || v is short || v is byte || v is uint || v is ulong || v is decimal)
                return Convert.ToString(v, INV);
            if (v is string) return Js((string)v);
            if (v is Enum) return Js(v.ToString());
            if (v is Vector2 || v is Vector3) return Js(v.ToString());
            UnityEngine.Object uo = v as UnityEngine.Object;
            if (uo != null || v is UnityEngine.Object)
            {
                if (uo == null) return "null"; // yok edilmiş obje
                GameObject go = uo as GameObject;
                Component co = uo as Component;
                if (go == null && co != null) go = co.gameObject;
                string ek = go != null ? ",\"aktif\":" + (go.activeInHierarchy ? "true" : "false") : "";
                // TextMeshPro vb. metin bileşenlerinde "text" özelliğini oku
                if (co != null)
                {
                    PropertyInfo p = co.GetType().GetProperty("text", BindingFlags.Instance | BindingFlags.Public);
                    if (p != null && p.PropertyType == typeof(string))
                    {
                        try { ek += ",\"metin\":" + Js((string)p.GetValue(co, null)); } catch { }
                    }
                }
                return "{\"ad\":" + Js(uo.name) + ek + "}";
            }
            IEnumerable en = v as IEnumerable;
            if (en != null && derinlik < 2)
            {
                var sb = new StringBuilder("[");
                int n = 0;
                foreach (object o in en)
                {
                    if (n > 0) sb.Append(',');
                    if (n >= 300) { sb.Append("\"...\""); break; }
                    sb.Append(Deger(o, derinlik + 1));
                    n++;
                }
                return sb.Append(']').ToString();
            }
            return Js(v.GetType().Name);
        }

        // ---------------- uç noktalar ----------------
        string Alanlar(string sinif)
        {
            Type t = Tip(sinif);
            object o = Ornek(t);
            var sb = new StringBuilder("{\"sinif\":" + Js(sinif) + ",\"ornek\":" + (o != null ? "true" : "false") + ",\"alanlar\":{");
            bool ilk = true;
            foreach (FieldInfo f in t.GetFields(BF))
            {
                if (o == null && !f.IsStatic) continue;
                object v;
                try { v = f.GetValue(f.IsStatic ? null : o); } catch { continue; }
                if (!ilk) sb.Append(',');
                ilk = false;
                sb.Append(Js(f.Name)).Append(':').Append(Deger(v, 0));
            }
            return sb.Append("}}").ToString();
        }

        string Metotlar(string sinif)
        {
            Type t = Tip(sinif);
            var sb = new StringBuilder("[");
            bool ilk = true;
            foreach (MethodInfo m in t.GetMethods(BF))
            {
                if (m.IsSpecialName) continue;
                var ps = new List<string>();
                foreach (ParameterInfo p in m.GetParameters()) ps.Add(p.ParameterType.Name + " " + p.Name);
                if (!ilk) sb.Append(',');
                ilk = false;
                sb.Append(Js(m.ReturnType.Name + " " + m.Name + "(" + string.Join(", ", ps.ToArray()) + ")"));
            }
            return sb.Append(']').ToString();
        }

        static object Cevir(string s, Type t)
        {
            if (t == typeof(string)) return s;
            if (t == typeof(int)) return int.Parse(s, INV);
            if (t == typeof(float)) return float.Parse(s, INV);
            if (t == typeof(double)) return double.Parse(s, INV);
            if (t == typeof(long)) return long.Parse(s, INV);
            if (t == typeof(bool)) return s == "1" || s.ToLowerInvariant() == "true";
            if (t.IsEnum) return Enum.Parse(t, s);
            throw new Exception("desteklenmeyen parametre tipi: " + t.Name);
        }

        string Cagir(string sinif, string metot, string[] args)
        {
            Type t = Tip(sinif);
            MethodInfo bulunan = null;
            foreach (MethodInfo m in t.GetMethods(BF))
                if (m.Name == metot && m.GetParameters().Length == args.Length) { bulunan = m; break; }
            if (bulunan == null) throw new Exception("metot bulunamadi: " + metot + " (" + args.Length + " arguman)");
            ParameterInfo[] ps = bulunan.GetParameters();
            object[] cevrilmis = new object[ps.Length];
            for (int i = 0; i < ps.Length; i++) cevrilmis[i] = Cevir(args[i], ps[i].ParameterType);
            object o = bulunan.IsStatic ? null : Ornek(t);
            if (o == null && !bulunan.IsStatic) throw new Exception("ornek yok: " + sinif);
            object sonuc = bulunan.Invoke(o, cevrilmis);
            // IEnumerator dönen metotlar (coroutine) başlatılmalı
            IEnumerator ie = sonuc as IEnumerator;
            if (ie != null && o is MonoBehaviour) { ((MonoBehaviour)o).StartCoroutine(ie); return "{\"tamam\":true,\"coroutine\":true}"; }
            return "{\"tamam\":true,\"sonuc\":" + Deger(sonuc, 0) + "}";
        }

        static Type TumTip(string ad)
        {
            foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = a.GetType(ad);
                if (t != null) return t;
            }
            return null;
        }

        static string Normal(string s)
        {
            if (s == null) return "";
            // TMP zengin metin etiketlerini temizle, boşlukları sadeleştir
            var sb = new StringBuilder();
            bool etiket = false;
            foreach (char c in s)
            {
                if (c == '<') { etiket = true; continue; }
                if (c == '>') { etiket = false; continue; }
                if (!etiket) sb.Append(char.IsWhiteSpace(c) ? ' ' : c);
            }
            return sb.ToString().Trim().ToLowerInvariant().Replace("  ", " ");
        }

        // metin == null -> aktif butonları listeler; değilse metni eşleşen ilk butonun onClick'ini çağırır
        string Butonlar(string metin)
        {
            Type bt = TumTip("UnityEngine.UI.Button");
            Type tmp = TumTip("TMPro.TMP_Text");
            Type leg = TumTip("UnityEngine.UI.Text");
            if (bt == null) throw new Exception("UnityEngine.UI.Button bulunamadi");
            PropertyInfo onClick = bt.GetProperty("onClick");
            PropertyInfo interact = bt.GetProperty("interactable");
            string aranan = metin != null ? Normal(metin) : null;
            var sb = new StringBuilder("[");
            bool ilk = true;
            foreach (UnityEngine.Object uo in UnityEngine.Object.FindObjectsOfType(bt))
            {
                Component b = (Component)uo;
                if (!b.gameObject.activeInHierarchy) continue;
                var yazilar = new List<string>();
                foreach (Type tt in new[] { tmp, leg })
                {
                    if (tt == null) continue;
                    foreach (Component c in b.GetComponentsInChildren(tt, false))
                    {
                        PropertyInfo p = tt.GetProperty("text");
                        string s = p != null ? p.GetValue(c, null) as string : null;
                        if (!string.IsNullOrEmpty(s)) yazilar.Add(s);
                    }
                }
                string hepsi = string.Join(" | ", yazilar.ToArray());
                bool aktif = interact == null || (bool)interact.GetValue(b, null);
                if (aranan != null)
                {
                    bool eslesti = Normal(b.gameObject.name) == aranan;
                    foreach (string y in yazilar) if (Normal(y) == aranan) eslesti = true;
                    if (!eslesti) continue;
                    if (!aktif) return "{\"tamam\":false,\"neden\":\"buton pasif\"}";
                    object ev = onClick.GetValue(b, null);
                    ev.GetType().GetMethod("Invoke", Type.EmptyTypes).Invoke(ev, null);
                    return "{\"tamam\":true,\"buton\":" + Js(b.gameObject.name) + "}";
                }
                if (!ilk) sb.Append(',');
                ilk = false;
                sb.Append("{\"ad\":").Append(Js(b.gameObject.name))
                  .Append(",\"metin\":").Append(Js(hepsi))
                  .Append(",\"tiklanabilir\":").Append(aktif ? "true" : "false").Append('}');
            }
            if (aranan != null) return "{\"tamam\":false,\"neden\":\"buton bulunamadi\"}";
            return sb.Append(']').ToString();
        }

        // Adı 'onek' ile başlayan AKTİF objelerdeki 'tip' bileşeninin basit alanları (+ buton durumu)
        string Bilesenler(string onek, string tip)
        {
            Type t = Tip(tip);
            Type bt = TumTip("UnityEngine.UI.Button");
            PropertyInfo interact = bt != null ? bt.GetProperty("interactable") : null;
            var sb = new StringBuilder("[");
            bool ilk = true;
            foreach (UnityEngine.Object uo in UnityEngine.Object.FindObjectsOfType(t))
            {
                Component c = (Component)uo;
                if (!c.gameObject.name.StartsWith(onek ?? "")) continue;
                if (!ilk) sb.Append(',');
                ilk = false;
                sb.Append("{\"ad\":").Append(Js(c.gameObject.name));
                Component b = bt != null ? c.GetComponent(bt) : null;
                if (b != null && interact != null)
                    sb.Append(",\"tiklanabilir\":").Append((bool)interact.GetValue(b, null) ? "true" : "false");
                sb.Append(",\"alanlar\":{");
                bool ilk2 = true;
                foreach (FieldInfo f in t.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                {
                    Type ft = f.FieldType;
                    if (!(ft.IsPrimitive || ft == typeof(string) || ft.IsEnum || ft == typeof(decimal))) continue;
                    if (!ilk2) sb.Append(',');
                    ilk2 = false;
                    sb.Append(Js(f.Name)).Append(':').Append(Deger(f.GetValue(c), 1));
                }
                sb.Append("}}");
            }
            return sb.Append(']').ToString();
        }

        // Bir objenin üzerine fare gelmiş gibi (OnPointerEnter) ya da çıkmış gibi (OnPointerExit) davran
        string UzerineGel(string ad, bool cik)
        {
            string metot = cik ? "OnPointerExit" : "OnPointerEnter";
            int sayi = 0;
            Type bt = TumTip("UnityEngine.UI.Button");
            foreach (UnityEngine.Object uo in UnityEngine.Object.FindObjectsOfType(typeof(Transform)))
            {
                Transform tr = (Transform)uo;
                if (tr.name != ad || !tr.gameObject.activeInHierarchy) continue;
                foreach (Component c in tr.GetComponents<Component>())
                {
                    if (c == null) continue;
                    if (bt != null && bt.IsInstanceOfType(c)) continue; // butonun kendi görsel hover'ı gereksiz
                    MethodInfo m = c.GetType().GetMethod(metot, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (m == null || m.GetParameters().Length != 1) continue;
                    m.Invoke(c, new object[] { null });
                    sayi++;
                }
                break;
            }
            return "{\"tamam\":" + (sayi > 0 ? "true" : "false") + ",\"cagrilan\":" + sayi + "}";
        }

        // Adı 'ad' olan objenin (gizli olsa bile) altındaki tüm yazılar
        string Metinler(string ad)
        {
            Type tmp = TumTip("TMPro.TMP_Text");
            var sb = new StringBuilder("[");
            bool ilk = true;
            foreach (UnityEngine.Object uo in Resources.FindObjectsOfTypeAll(typeof(Transform)))
            {
                Transform tr = (Transform)uo;
                if (tr.name != ad || !tr.gameObject.scene.IsValid()) continue;
                if (tmp != null)
                    foreach (Component c in tr.GetComponentsInChildren(tmp, true))
                    {
                        string m = tmp.GetProperty("text").GetValue(c, null) as string;
                        if (string.IsNullOrEmpty(m)) continue;
                        if (!ilk) sb.Append(',');
                        ilk = false;
                        sb.Append("{\"obje\":").Append(Js(c.gameObject.name)).Append(",\"metin\":").Append(Js(m)).Append('}');
                    }
                break;
            }
            return sb.Append(']').ToString();
        }

        string Ayarla(string sinif, string alan, string deger)
        {
            Type t = Tip(sinif);
            FieldInfo f = t.GetField(alan, BF);
            if (f == null) throw new Exception("alan yok: " + alan);
            object o = f.IsStatic ? null : Ornek(t);
            f.SetValue(o, Cevir(deger, f.FieldType));
            return "{\"tamam\":true}";
        }

        string Durum()
        {
            var sb = new StringBuilder("{");
            sb.Append("\"ekran\":[").Append(Screen.width).Append(',').Append(Screen.height).Append(']');
            sb.Append(",\"sahne\":").Append(Js(UnityEngine.SceneManagement.SceneManager.GetActiveScene().name));
            sb.Append(",\"cember\":").Append(CemberBilgisi());

            // Maden oturumu
            Type ms = oyunAsm.GetType("SetMiningSceen");
            object mso = ms != null ? Ornek(ms) : null;
            if (mso != null)
            {
                foreach (string ad in new[] { "isInMiningSession", "isTimeStarted", "timeLeft", "currentTime", "rocksMinedThisRound", "totalRocksOnScreen", "isGoldenHourActive" })
                {
                    FieldInfo f = ms.GetField(ad, BF);
                    if (f != null) sb.Append(",\"").Append(ad).Append("\":").Append(Deger(f.GetValue(mso), 1));
                }
            }

            // Halolar (Halo kartı: çember üzerinde tutulunca emilir)
            if (mso != null)
            {
                FieldInfo hf = ms.GetField("haloParent", BF);
                object hp0 = hf != null ? hf.GetValue(mso) : null;
                Transform ht = hp0 as Transform;
                if (ht == null && hp0 is GameObject) ht = ((GameObject)hp0).transform;
                Camera hcam = Camera.main;
                sb.Append(",\"halolar\":[");
                bool hilk = true;
                if (ht != null && hcam != null)
                    foreach (Transform c in ht)
                    {
                        if (!c.gameObject.activeInHierarchy) continue;
                        Vector3 hp = hcam.WorldToScreenPoint(c.position);
                        if (!hilk) sb.Append(',');
                        hilk = false;
                        sb.Append("{\"x\":").Append(hp.x.ToString("0.0", INV)).Append(",\"y\":").Append((Screen.height - hp.y).ToString("0.0", INV)).Append('}');
                    }
                sb.Append(']');
            }

            // Level
            Type lv = oyunAsm.GetType("LevelMechanics");
            object lvo = lv != null ? Ornek(lv) : null;
            if (lvo != null)
            {
                foreach (string ad in new[] { "level", "currentXP", "xpNeedForNextLvl", "totalTalentPoints", "totalMasteryPoints" })
                {
                    FieldInfo f = lv.GetField(ad, BF);
                    if (f != null) sb.Append(",\"").Append(ad).Append("\":").Append(Deger(f.GetValue(lvo), 1));
                }
            }

            // Kayalar
            Camera cam = Camera.main;
            sb.Append(",\"kayalar\":[");
            Type rt = oyunAsm.GetType("RockMechanics");
            if (rt != null && cam != null)
            {
                FieldInfo[] alanlar = rt.GetFields(BF);
                FieldInfo hp = rt.GetField("rockHP", BF);
                FieldInfo gem = rt.GetField("currentGem", BF);
                FieldInfo eser = rt.GetField("artifactStuckParent", BF);
                bool ilk = true;
                foreach (UnityEngine.Object uo in UnityEngine.Object.FindObjectsOfType(rt))
                {
                    MonoBehaviour mb = (MonoBehaviour)uo;
                    Vector3 p = cam.WorldToScreenPoint(mb.transform.position);
                    if (!ilk) sb.Append(',');
                    ilk = false;
                    sb.Append("{\"x\":").Append(p.x.ToString("0.0", INV))
                      .Append(",\"y\":").Append((Screen.height - p.y).ToString("0.0", INV))
                      .Append(",\"id\":").Append(mb.GetInstanceID());
                    if (hp != null) sb.Append(",\"hp\":").Append(Deger(hp.GetValue(mb), 1));
                    // doğru olan tüm bool bayrakları (isGoldChunk, isFullSilver, didRubySpawn, isRockBroken...)
                    sb.Append(",\"bayrak\":[");
                    bool ib = true;
                    foreach (FieldInfo f in alanlar)
                    {
                        if (f.FieldType != typeof(bool) || f.IsStatic) continue;
                        if (!(bool)f.GetValue(mb)) continue;
                        if (!ib) sb.Append(',');
                        ib = false;
                        sb.Append(Js(f.Name));
                    }
                    sb.Append(']');
                    if (gem != null)
                    {
                        object g = gem.GetValue(mb);
                        UnityEngine.Object gu = g as UnityEngine.Object;
                        if (gu != null)
                        {
                            GameObject gg = gu as GameObject;
                            if (gg == null && gu is Component) gg = ((Component)gu).gameObject;
                            if (gg == null || gg.activeInHierarchy) sb.Append(",\"mucevher\":").Append(Js(gu.name));
                        }
                    }
                    if (eser != null)
                    {
                        object e = eser.GetValue(mb);
                        Transform et = e as Transform;
                        if (et == null && e is GameObject) et = ((GameObject)e).transform;
                        if (et != null)
                        {
                            int aktif = 0;
                            foreach (Transform c in et) if (c.gameObject.activeSelf) aktif++;
                            if (aktif > 0) sb.Append(",\"eser\":").Append(aktif);
                        }
                    }
                    sb.Append('}');
                }
            }
            sb.Append(']');
            return sb.Append('}').ToString();
        }
    }
}
