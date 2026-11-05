@echo off
rem Kopru eklentisini derler ve oyunun BepInEx\plugins klasorune kopyalar.
cd /d "%~dp0"
set OYUN=C:\Program Files (x86)\Steam\steamapps\common\Keep on Mining! - Worlds
set M=%OYUN%\Keep on Mining! - Worlds_Data\Managed
set B=%OYUN%\BepInEx\core
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:library /optimize /nostdlib /noconfig /out:KomKopru.dll ^
 /r:"%M%\mscorlib.dll" /r:"%M%\System.dll" /r:"%M%\System.Core.dll" /r:"%M%\netstandard.dll" ^
 /r:"%M%\UnityEngine.dll" /r:"%M%\UnityEngine.CoreModule.dll" ^
 /r:"%B%\BepInEx.dll" ^
 KomKopru.cs
if errorlevel 1 (echo DERLEME HATASI & exit /b 1)
echo Derlendi.
copy /y KomKopru.dll "%OYUN%\BepInEx\plugins\" >nul 2>&1
if errorlevel 1 (echo Oyun acik oldugu icin kopyalanamadi - bot oyunu acarken kuracak.) else (echo Oyuna kuruldu.)
