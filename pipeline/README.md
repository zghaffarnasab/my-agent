# پایپ‌لاین داشبورد فیلمساز (Funds و Events)

این پوشه جدا از دستیار جیمیل (`app/`) است: دیتابیس Postgres خودش را دارد و با فایل Compose خودش اجرا می‌شود. به کانتینرهای دستیار جیمیل دست نمی‌زند.

کاری که الان انجام می‌دهد (نسخه‌ی اول):

1. صفحه‌های رسمی فهرست‌شده در `sources.json` را می‌خواند (فعلاً BFI، Doc Society، Whickers و Sheffield DocFest).
2. متن اصلی صفحه را با trafilatura جدا می‌کند و hash می‌گیرد. فقط اگر متن عوض شده باشد snapshot تازه ذخیره می‌شود.
3. snapshot تازه را با پرامپت `prompts/extract-v1.txt` به Claude می‌دهد.
4. کد بررسی می‌کند که هر تاریخ و مبلغ یک نقل‌قول داشته باشد که **عیناً** در متن صفحه پیدا شود و خود عدد هم داخل همان نقل‌قول باشد. هر چیزی که رد شود در `extraction_runs.rejected_items` ثبت می‌شود.
5. نتیجه به‌صورت `draft` در Postgres ذخیره می‌شود. هیچ چیزی خودکار منتشر نمی‌شود.

هنوز ندارد: RSS و خبرنامه‌ها.

## راه‌اندازی روی سرور (یک بار)

```bash
cd ~/my-agent && git pull
cp pipeline/.env.example pipeline/.env
nano pipeline/.env        # POSTGRES_PASSWORD و ANTHROPIC_API_KEY را پر کن

sudo docker compose -f pipeline/docker-compose.yml up -d db
sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline migrate
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline seed
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline run
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline status
```

`status` تعداد رکوردها، صف بررسی و تاریخ‌های پیش رو را نشان می‌دهد. اگر صفحه‌ای خطا داشت (مثلاً `HTTP 403` یا «no main text found»)، آن صفحه احتمالاً جاوااسکریپت لازم دارد و در فاز بعد با Playwright خوانده می‌شود.

## صفحه‌ی بررسی در داشبورد (یک بار)

داشبورد جیمیل یک صفحه‌ی «داشبورد فیلم» دارد که در آن هر draft را با نقل‌قول‌هایش می‌بینی و تأیید یا رد می‌کنی. برای روشن کردنش:

1. دیتابیس را یک بار دوباره بالا بیاور تا به شبکه‌ی داشبورد وصل شود (داده‌ها پاک نمی‌شوند):
   ```bash
   cd ~/my-agent && git pull
   sudo docker compose -f pipeline/docker-compose.yml up -d db
   ```
2. در فایل `.env` اصلی (نه `pipeline/.env`) این خط را اضافه کن. به‌جای `PASSWORD` همان `POSTGRES_PASSWORD` فایل `pipeline/.env` را بگذار:
   ```
   FILMDASH_DATABASE_URL=postgresql://filmdash:PASSWORD@filmdash-db:5432/filmdash
   ```
3. داشبورد را مثل همیشه به‌روز کن:
   ```bash
   sudo docker compose cp web:/data/app.db ./backup.db && sudo docker compose up -d --build
   ```

بعد در داشبورد، کنار «تنظیمات»، لینک «داشبورد فیلم» را می‌بینی.

## فرستادن به سایت Wix (یک بار)

فقط فاندها و رویدادهایی که در «داشبورد فیلم» **تأیید** کرده‌ای به دو کالکشن CMS در سایت Wix می‌روند: `FilmFunds` و `FilmEvents`. پیش‌نویس‌ها هیچ‌وقت نمی‌روند. اگر چیزی را بعداً رد کنی، از Wix هم پاک می‌شود. این ارسال یک‌طرفه است: Postgres منبع اصلی است و تغییر دستی در CMS با اجرای بعدی بازنویسی می‌شود.

1. در Wix یک API key بساز: Account Settings → API Keys → Generate API Key. دسترسی **Wix Data** (مدیریت کالکشن‌ها و نوشتن آیتم‌ها) را بده و سایتت را انتخاب کن.
2. شناسه‌ی سایت (Site ID) را از آدرس داشبورد سایت بردار: عدد/حروف بعد از `/dashboard/`.
3. این دو خط را به `pipeline/.env` اضافه کن:
   ```
   WIX_API_KEY=...
   WIX_SITE_ID=...
   ```
4. اول ببین چه چیزی فرستاده می‌شود (هیچ چیزی به Wix نمی‌رود):
   ```bash
   sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline wix-sync --dry-run
   ```
5. بعد واقعاً بفرست (بار اول دو کالکشن را هم می‌سازد):
   ```bash
   sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline wix-sync
   ```

از این به بعد اجرای روزانه‌ی `run` بعد از خواندن صفحه‌ها خودش `wix-sync` را هم انجام می‌دهد؛ پس چیزی که امروز تأیید کنی فردا صبح در Wix است (یا همان لحظه با دستور بالا).

کالکشن‌ها روی سایت دیده نمی‌شوند تا خودت در ادیتور Wix آن‌ها را به یک صفحه وصل کنی (مثلاً یک Repeater یا یک dynamic page). فیلد `displayStatus` برای چیزهایی که مهلتشان گذشته `expired` است؛ در صفحه فیلتر کن که فقط `published` نشان داده شود.

## اجرای خودکار روزانه

```bash
sudo crontab -e
```

و این خط را اضافه کن (هر روز ساعت ۶ صبح به وقت سرور):

```
0 6 * * * cd /home/ubuntu/my-agent && docker compose -f pipeline/docker-compose.yml run --rm pipeline run >> /var/log/filmdash.log 2>&1
```

هر صفحه پیش‌فرض هفته‌ای یک بار خوانده می‌شود (`check_interval` در جدول `sources`). اگر صفحه عوض نشده باشد، Claude صدا زده نمی‌شود و هزینه‌ای ندارد.

## بعد از هر git pull

```bash
sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline migrate
```

## دیدن داده‌ها

```bash
sudo docker compose -f pipeline/docker-compose.yml exec db psql -U filmdash filmdash
```

مثلاً `SELECT * FROM review_queue;` یا `SELECT name, kind, status, date_value, source_quote FROM current_dates d JOIN funds f ON f.id = d.fund_id;`

پشتیبان‌گیری:

```bash
sudo docker compose -f pipeline/docker-compose.yml exec db pg_dump -U filmdash filmdash > filmdash-backup.sql
```

هرگز `docker compose down -v` نزن: داده‌ها پاک می‌شوند.

## اضافه کردن صفحه‌ی تازه

صفحه را به `sources.json` اضافه کن و `seed` را دوباره اجرا کن. `tier` برای صفحه‌ی خود نهاد `official` است؛ برای سایت‌های فهرست‌کننده `aggregator` (تاریخ‌هایشان هیچ‌وقت «confirmed» نمی‌شوند).

## تست‌ها

تست‌های بدون دیتابیس با بقیه‌ی تست‌ها اجرا می‌شوند. تست کامل با یک Postgres خالی:

```bash
PIPELINE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/filmdash_test .venv/bin/python -m pytest tests/test_pipeline_db.py
```

این تست schema دیتابیس داده‌شده را پاک می‌کند؛ هرگز آن را به دیتابیس واقعی وصل نکن. در تست‌ها Claude و وب جعلی‌اند.
