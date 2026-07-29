# Deal Watcher — نسخة Windows

هذه النسخة الأولية تنفذ:

- حفظ المنتجات في SQLite داخل `data/tracker.db`.
- حفظ سجل الأسعار.
- استئناف المنتجات بعد إغلاق الجهاز.
- فحص المنتجات التي فات موعدها مباشرة بعد تشغيل الـWorker.
- استخراج السعر من Amazon.sa باستخدام Playwright.
- تنبيه Telegram عند الوصول للسعر المستهدف أو حدوث انخفاض.
- موافقة بشرية من مرحلتين قبل حفظ المنتج.
- MCP Server لربطه مع Hermes لاحقًا.

## 1) التثبيت

افتح PowerShell داخل مجلد المشروع:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

## 2) إعداد Telegram

افتح الملف:

```powershell
notepad .env
```

ضع:

```env
TELEGRAM_BOT_TOKEN=ضع_التوكن_هنا
TELEGRAM_CHAT_ID=ضع_رقم_المحادثة_هنا
```

لا ترفع `.env` إلى Git ولا ترسل التوكن لأحد.

## 3) اختبار إضافة منتج يدويًا

المعاينة لا تحفظ المنتج:

```powershell
.\.venv\Scripts\python.exe -m src.cli preview "رابط Amazon.sa" --target 250
```

سيظهر رمز موافقة. بعد التأكد من البيانات:

```powershell
.\.venv\Scripts\python.exe -m src.cli confirm رمز_الموافقة
```

عرض المنتجات:

```powershell
.\.venv\Scripts\python.exe -m src.cli list
```

## 4) تشغيل الفاحص

```powershell
.\run-worker.cmd
```

اتركه يعمل أثناء الاختبار. للخروج اضغط `Ctrl+C`.

السجل موجود في:

```text
logs\worker.log
```

## 5) التشغيل التلقائي مع Windows

بعد نجاح الاختبار:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-autostart.ps1
```

سيتم إنشاء Windows Scheduled Task باسم:

```text
DealWatcherWorker
```

لتشغيلها فورًا:

```powershell
schtasks /Run /TN "DealWatcherWorker"
```

لحذف التشغيل التلقائي:

```powershell
.\uninstall-autostart.ps1
```

## كيف يعمل الاستئناف؟

قاعدة SQLite تحفظ المنتجات والأسعار على القرص. عند تشغيل الـWorker:

1. يقرأ المنتجات النشطة.
2. يقارن `next_check_at` بالوقت الحالي.
3. أي منتج فات موعده أثناء إغلاق الجهاز يُفحص مباشرة.
4. بعد الفحص، يُحدد الموعد التالي.

الجهاز لا يستطيع الفحص وهو مطفأ، لكنه لا يفقد المنتجات أو تاريخها.

## ملاحظة Amazon

السكربت لا يحاول تجاوز CAPTCHA أو وسائل حماية Amazon. عند ظهور صفحة تحقق،
يسجل الخطأ ويعيد المحاولة لاحقًا. النسخة الحالية تدعم Amazon.sa فقط.
