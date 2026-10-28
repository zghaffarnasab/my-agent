"""App version and change history.

When releasing a new version: bump VERSION and add an entry at the TOP of CHANGELOG.
Every entry is bilingual: "title" and "changes" hold both "en" and "fa".
Numbering: MAJOR.MINOR.PATCH
  - PATCH (1.2.0 -> 1.2.1): small fixes
  - MINOR (1.2.0 -> 1.3.0): new features
  - MAJOR (1.x -> 2.0.0): big redesigns or changes that need extra setup
"""

VERSION = "1.20.0"

CHANGELOG = [
    {
        "version": "1.20.0",
        "date": "2026-10-28",
        "title": {
            "en": "Stronger login security",
            "fa": "امنیت بیشتر برای ورود",
        },
        "changes": {
            "en": [
                "After 5 wrong passwords from the same address, logging in from there is locked for 15 minutes.",
                "New \"Sign out everywhere\" button on the Settings page. A login now lasts 7 days instead of 14.",
                "The automatic API pages (/docs, /openapi.json) are switched off, so the app's address list is no longer public.",
                "Safer browser headers (no framing by other sites, HTTPS only), and form posts from other websites are refused.",
            ],
            "fa": [
                "بعد از ۵ رمز اشتباه از یک آدرس، ورود از آنجا ۱۵ دقیقه قفل می‌شود.",
                "دکمه‌ی جدید «خروج از همه‌ی دستگاه‌ها» در صفحه‌ی تنظیمات. هر ورود حالا ۷ روز معتبر است به‌جای ۱۴ روز.",
                "صفحه‌های خودکار API (/docs و /openapi.json) خاموش شدند و فهرست آدرس‌های برنامه دیگر عمومی نیست.",
                "هدرهای امن‌تر برای مرورگر (سایت دیگری نمی‌تواند برنامه را داخل خودش نشان دهد، فقط HTTPS) و فرم‌هایی که از سایت‌های دیگر فرستاده شوند رد می‌شوند.",
            ],
        },
    },
    {
        "version": "1.18.0",
        "date": "2026-10-28",
        "title": {
            "en": "Priorities on the task board",
            "fa": "اولویت در برد تسک‌ها",
        },
        "changes": {
            "en": [
                "Every task has a priority: high tasks are red, medium tasks are orange, and low tasks keep the plain look.",
                "Choose the priority when you add or edit a task. Existing tasks start as low priority.",
            ],
            "fa": [
                "هر تسک اولویت دارد: اولویت بالا قرمز، اولویت متوسط نارنجی، و اولویت پایین مثل قبل بی‌رنگ.",
                "اولویت را موقع ساختن یا ویرایش تسک انتخاب کن. تسک‌های قبلی با اولویت پایین شروع می‌کنند.",
            ],
        },
    },
    {
        "version": "1.17.0",
        "date": "2026-10-28",
        "title": {
            "en": "Pictures in task board tasks",
            "fa": "عکس در تسک‌های برد",
        },
        "changes": {
            "en": [
                "A task can now hold pictures: choose files, paste a screenshot into the notes box, or drop image files on the form.",
                "The pictures appear as small previews on the card; click one to see it large. Remove a picture from the task's edit form.",
                "PNG, JPEG, GIF and WebP up to 5 MB each, at most 10 per task. Pictures are kept in the app's own database, so the usual backup includes them.",
            ],
            "fa": [
                "تسک حالا می‌تواند عکس داشته باشد: فایل انتخاب کن، اسکرین‌شات را در کادر توضیحات paste کن یا فایل عکس را روی فرم بکش.",
                "عکس‌ها به‌صورت پیش‌نمایش کوچک روی کارت دیده می‌شوند؛ با کلیک بزرگ می‌شوند. حذف عکس از فرم ویرایش تسک.",
                "PNG، JPEG، GIF و WebP هر کدام تا ۵ مگابایت، حداکثر ۱۰ عکس برای هر تسک. عکس‌ها در دیتابیس خود برنامه ذخیره می‌شوند، پس بکاپ معمول آن‌ها را هم دارد.",
            ],
        },
    },
    {
        "version": "1.16.0",
        "date": "2026-10-26",
        "title": {
            "en": "Website requests show the visitor's links and files",
            "fa": "لینک‌ها و فایل‌های متقاضی در درخواست‌های سایت",
        },
        "changes": {
            "en": [
                "The website form now lets visitors share links (Google Drive, YouTube, Vimeo, ...) and attach a screenplay, treatment or synopsis. Both appear on the request page under the message.",
                "Files download with one click (always as a download, never opened inside the app). Links are only shown, never opened by the app.",
            ],
            "fa": [
                "فرم سایت حالا به متقاضی اجازه می‌دهد لینک (گوگل درایو، یوتیوب، ویمئو و ...) بفرستد و فیلم‌نامه، طرح یا خلاصه داستان پیوست کند. هر دو در صفحه‌ی درخواست زیر پیام دیده می‌شوند.",
                "فایل‌ها با یک کلیک دانلود می‌شوند (همیشه دانلود، هیچ‌وقت داخل برنامه باز نمی‌شوند). لینک‌ها فقط نمایش داده می‌شوند و برنامه آن‌ها را باز نمی‌کند.",
            ],
        },
    },
    {
        "version": "1.15.1",
        "date": "2026-10-25",
        "title": {
            "en": "A newer, cheaper model reads the emails",
            "fa": "مدل جدیدتر و ارزان‌تر ایمیل‌ها را می‌خواند",
        },
        "changes": {
            "en": [
                "The cheap model that sorts emails, finds events and matches site requests is now Claude Haiku 5.5 (was Haiku 4.5): about ten times cheaper per token and better at following the rules.",
                "New setting CLASSIFY_EFFORT (default low) controls how much that model thinks before answering.",
            ],
            "fa": [
                "مدل ارزانی که ایمیل‌ها را دسته‌بندی می‌کند، رویدادها را پیدا می‌کند و درخواست‌های سایت را تطبیق می‌دهد حالا Claude Haiku 5.5 است (قبلاً Haiku 4.5): هر توکن حدود ده برابر ارزان‌تر و در رعایت قواعد دقیق‌تر.",
                "تنظیم تازه‌ی CLASSIFY_EFFORT (پیش‌فرض low) تعیین می‌کند این مدل پیش از جواب دادن چقدر فکر کند.",
            ],
        },
    },
    {
        "version": "1.15.0",
        "date": "2026-10-21",
        "title": {
            "en": "A simple task board",
            "fa": "یک برد تسک ساده",
        },
        "changes": {
            "en": [
                "New \"Task board\" page in the menu: unfinished work in three columns (To do, In progress, Done). Drag a card to another column, or use its arrow buttons.",
                "Every task belongs to one person, shown on the card with their own color, and the buttons at the top show one person's tasks only.",
                "Tasks can have notes and an optional due date; overdue tasks are marked in red. Edit or delete a task from its card.",
                "Type the names of the people on the board on the Settings page (separated by commas).",
            ],
            "fa": [
                "صفحه‌ی تازه‌ی «برد تسک‌ها» در منو: کارهای ناتمام در سه ستون (برای انجام، در حال انجام، انجام شد). کارت را به ستون دیگر بکش یا از دکمه‌های فلش روی کارت استفاده کن.",
                "هر تسک مال یک نفر است که با رنگ خودش روی کارت دیده می‌شود، و دکمه‌های بالای صفحه فقط تسک‌های یک نفر را نشان می‌دهند.",
                "تسک می‌تواند توضیحات و مهلت اختیاری داشته باشد؛ تسک‌هایی که مهلتشان گذشته قرمز می‌شوند. ویرایش و حذف از روی خود کارت.",
                "نام افراد برد را در صفحه‌ی تنظیمات بنویس (با ویرگول جدا کن).",
            ],
        },
    },
    {
        "version": "1.14.0",
        "date": "2026-10-20",
        "title": {
            "en": "Urgent emails stand out, and deadlines become calendar suggestions",
            "fa": "ایمیل‌های فوری برجسته می‌شوند و مهلت‌ها پیشنهاد تقویم می‌شوند",
        },
        "changes": {
            "en": [
                "Emails where something real is at stake (a government, tax or company-registry deadline, a final reminder, a failed payment, an account at risk) are marked Urgent: the row is red, sits at the top of its tab, and the email shows what is at stake.",
                "Deadlines with a date (for example \"file by 21/10/2026\") now also appear as all-day \"Deadline: ...\" suggestions you can add to Google Calendar, even when the email needs no reply. Newsletters and promotions are left out.",
                "\"Check this email again\" now reads the whole email again, so older emails can be marked urgent and get their deadline suggestions too. Your draft and the email's tab do not change.",
            ],
            "fa": [
                "ایمیل‌هایی که پای چیز مهمی در میان است (مهلت اداره‌ی دولتی، مالیات یا ثبت شرکت، یادآوری نهایی، پرداخت ناموفق، خطر بسته شدن حساب) «فوری» علامت می‌خورند: ردیف قرمز می‌شود، بالای فهرست همان بخش می‌آید و در خود ایمیل نوشته می‌شود چه چیزی در خطر است.",
                "مهلت‌های تاریخ‌دار (مثلاً «تا ۲۱/۱۰/۲۰۲۶ ثبت شود») حالا به‌صورت پیشنهاد تمام‌روزِ «مهلت: ...» هم می‌آیند تا به تقویم گوگل اضافه کنی، حتی اگر ایمیل جواب نخواهد. خبرنامه‌ها و تبلیغات حساب نمی‌شوند.",
                "دکمه‌ی «بررسی دوباره‌ی این ایمیل» حالا کل ایمیل را دوباره می‌خواند، پس ایمیل‌های قبلی هم می‌توانند فوری علامت بخورند و پیشنهاد مهلت بگیرند. پیش‌نویس و بخش ایمیل عوض نمی‌شود.",
            ],
        },
    },
    {
        "version": "1.13.1",
        "date": "2026-10-20",
        "title": {
            "en": "Tidier pages and one menu everywhere",
            "fa": "صفحه‌های مرتب‌تر و یک منوی یکسان در همه‌جا",
        },
        "changes": {
            "en": [
                "Every page now has the same menu at the top (Reply queue, Film dashboard, Website requests, Website visits, Settings); the current page is underlined. Language and Log out are always on the right.",
                "\"Check for new emails\" and \"Change account\" moved next to the Reply queue title. Detail pages have a \"Back to the list\" link above the title.",
                "Event cards: the start and end time boxes no longer stick out of the card.",
                "Film dashboard: in Persian the date sits at the end of each row again; quotes show readable field names; the approve note no longer mentions Wix.",
                "Settings and Changelog use the same page width as the other pages.",
            ],
            "fa": [
                "حالا بالای همه‌ی صفحه‌ها یک منوی یکسان هست (صف جواب‌ها، داشبورد فیلم، درخواست‌های سایت، بازدیدهای سایت، تنظیمات) و صفحه‌ی فعلی زیرخط دارد. زبان و خروج همیشه در گوشه‌ی بالا هستند.",
                "«بررسی ایمیل‌های جدید» و «تغییر حساب» کنار عنوان صف جواب‌ها آمدند. صفحه‌های جزئیات بالای عنوان یک پیوند «بازگشت به فهرست» دارند.",
                "کارت رویدادها: کادرهای ساعت شروع و پایان دیگر از کارت بیرون نمی‌زنند.",
                "داشبورد فیلم: در فارسی تاریخ دوباره در انتهای هر ردیف است؛ نقل‌قول‌ها نام خوانای فیلد را نشان می‌دهند؛ توضیح تأیید دیگر از Wix حرف نمی‌زند.",
                "تنظیمات و تاریخچه‌ی تغییرات همان عرض صفحه‌های دیگر را دارند.",
            ],
        },
    },
    {
        "version": "1.13.0",
        "date": "2026-10-19",
        "title": {
            "en": "Website visit statistics",
            "fa": "آمار بازدید سایت",
        },
        "changes": {
            "en": [
                "New page \"Website visits\" (/stats): visitors and page views of the company website for the last 7, 30 or 90 days, views per day, the most visited pages, which websites people came from, phone or computer, and the site language they used.",
                "The website counts visits itself, without cookies and without any outside analytics service; no IP address is stored.",
            ],
            "fa": [
                "صفحه‌ی تازه‌ی «بازدیدهای سایت» (/stats): تعداد بازدیدکننده‌ها و بازدید صفحه‌های سایت شرکت در ۷، ۳۰ یا ۹۰ روز گذشته، بازدید هر روز، صفحه‌های پربازدید، سایت‌هایی که بازدیدکننده‌ها از آن‌ها آمده‌اند، گوشی یا کامپیوتر، و زبانی که در سایت انتخاب کرده‌اند.",
                "سایت خودش بازدیدها را می‌شمارد، بدون کوکی و بدون هیچ سرویس آمار بیرونی؛ هیچ آدرس IP ذخیره نمی‌شود.",
            ],
        },
    },
    {
        "version": "1.12.0",
        "date": "2026-10-19",
        "title": {
            "en": "Website requests: registrations on an organiser's own site",
            "fa": "درخواست‌های سایت: ثبت‌نام در سایت خود برگزارکننده",
        },
        "changes": {
            "en": [
                "When an event or fund takes registrations through a form on its own site (or FilmFreeway), the request page now shows everything that form needs, ready to copy one by one or all at once.",
                "After registering by hand, \"I registered on their site\" records the date, an optional reference number and a note, so the request is tracked like the emailed ones.",
                "For these registrations you can record the organiser's answer yourself (received, accepted, not accepted, needs more) and open a short update email to the visitor.",
            ],
            "fa": [
                "وقتی ثبت‌نام یک رویداد یا فاند با فرمی در سایت خودش (یا FilmFreeway) است، صفحه‌ی درخواست حالا همه‌ی اطلاعات لازم آن فرم را آماده‌ی کپی نشان می‌دهد، تک‌تک یا همه با هم.",
                "بعد از ثبت‌نام دستی، دکمه‌ی «در سایتشان ثبت کردم» تاریخ، شماره‌ی پیگیری (اختیاری) و یک یادداشت را نگه می‌دارد تا پیگیری درخواست مثل ثبت‌نام‌های ایمیلی در سیستم بماند.",
                "برای این ثبت‌نام‌ها می‌توانی جواب برگزارکننده را خودت ثبت کنی (دریافت شد، پذیرفته شد، پذیرفته نشد، اطلاعات بیشتر لازم است) و یک ایمیل کوتاه خبر برای متقاضی باز کنی.",
            ],
        },
    },
    {
        "version": "1.11.1",
        "date": "2026-10-19",
        "title": {
            "en": "Film dashboard: who can apply, in the list",
            "fa": "داشبورد فیلم: چه کسی می‌تواند درخواست بدهد، در فهرست",
        },
        "changes": {
            "en": [
                "Each fund and event in the review list now shows an \"Open to\" badge next to the UK badge (for example DK, FI, NO, SE, or worldwide), when the page says who may apply.",
            ],
            "fa": [
                "هر فاند و رویداد در فهرست بررسی حالا کنار نشان بریتانیا یک نشان «باز برای» هم دارد (مثلاً DK، FI، NO، SE یا همه‌ی کشورها)، اگر صفحه گفته باشد چه کسانی می‌توانند درخواست بدهند.",
            ],
        },
    },
    {
        "version": "1.11.0",
        "date": "2026-10-19",
        "title": {
            "en": "Funds and events across Europe",
            "fa": "فاندها و رویدادهای سراسر اروپا",
        },
        "changes": {
            "en": [
                "The pipeline now also watches 17 European pages: Eurimages, Creative Europe MEDIA, Hubert Bals Fund, Screen Ireland, the Danish and Swedish film institutes, Nordisk Film & TV Fond, CNC, CPH:DOX, DOK Leipzig, IDFA, Visions du Réel, Berlinale, TorinoFilmLab, Biennale College and Thessaloniki. All UK sources stay.",
                "Each fund and event now records which countries may apply (\"open to\"), and events record the country they take place in. The UK eligibility badge stays as it was.",
                "Website request suggestions use this: a visitor from Germany is no longer offered a fund only open to Denmark, and a UK visitor is not offered Creative Europe MEDIA calls.",
                "The film dashboard shows the country next to each organisation and the \"open to\" list on the detail page.",
            ],
            "fa": [
                "پایپ‌لاین حالا ۱۷ صفحه‌ی اروپایی را هم دنبال می‌کند: Eurimages، Creative Europe MEDIA، Hubert Bals Fund، Screen Ireland، مؤسسه‌های فیلم دانمارک و سوئد، Nordisk Film & TV Fond، CNC، CPH:DOX، DOK Leipzig، IDFA، Visions du Réel، برلیناله، TorinoFilmLab، Biennale College و تسالونیکی. همه‌ی منابع بریتانیا سر جایشان هستند.",
                "برای هر فاند و رویداد ثبت می‌شود که متقاضی از چه کشورهایی می‌تواند درخواست بدهد، و برای رویدادها کشور برگزاری. نشان «مناسب بریتانیا» مثل قبل می‌ماند.",
                "پیشنهادهای درخواست‌های سایت از این استفاده می‌کنند: به متقاضی آلمانی فاندی که فقط برای دانمارک باز است پیشنهاد نمی‌شود، و به متقاضی بریتانیایی فراخوان‌های Creative Europe MEDIA.",
                "داشبورد فیلم کشور هر سازمان را کنار نامش، و فهرست کشورهای مجاز را در صفحه‌ی جزئیات نشان می‌دهد.",
            ],
        },
    },
    {
        "version": "1.10.0",
        "date": "2026-10-18",
        "title": {
            "en": "Website requests: suggestions, offer email and registration",
            "fa": "درخواست‌های سایت: پیشنهاد، ایمیل پیشنهاد و ثبت‌نام",
        },
        "changes": {
            "en": [
                "New \"Website requests\" page next to the film dashboard: every request sent through the website form, by status.",
                "Each new request gets up to 5 suggestions from the published funds and events that are still open, chosen by what the visitor needs (festival, fund, workshop), film type, stage and country, each with a one-line reason in the visitor's language.",
                "Tick the right ones, add a note, and an email to the visitor is written for you. Edit it and send it from the website mailbox, or open it in your own mail app.",
                "The offer email links to a confirmation page on the website (REQUESTS_CONFIRM_URL): the visitor ticks the options they want, sends their film details and accepts the terms. Their answer appears on the request by itself.",
                "Registrations by email are written in English with the film details, and sent from the company address to the organiser with the visitor in copy, after you check them and press Send.",
                "Organisers' replies are read from the company inbox over IMAP (REQUESTS_IMAP_*, read-only, nothing marked as read) and shown under each registration as received, accepted, not accepted or needs more, with a short summary and a ready note to the visitor.",
                "Nothing is sent to anyone without your click. Registrations on other websites (and FilmFreeway) are still done by hand.",
            ],
            "fa": [
                "صفحه‌ی تازه‌ی «درخواست‌های سایت» کنار داشبورد فیلم: همه‌ی درخواست‌هایی که از فرم سایت می‌رسند، بر اساس وضعیت.",
                "برای هر درخواست تازه تا ۵ پیشنهاد از فاندها و رویدادهای منتشرشده‌ای که هنوز باز هستند پیدا می‌شود، بر اساس نیاز متقاضی (جشنواره، بودجه، کارگاه)، نوع فیلم، مرحله و کشور، هر کدام با یک خط دلیل به زبان خود متقاضی.",
                "گزینه‌های درست را تیک بزن و یادداشت بگذار تا ایمیل متقاضی برایت نوشته شود. ویرایشش کن و از صندوق ایمیل سایت بفرست، یا در برنامه‌ی ایمیل خودت بازش کن.",
                "ایمیل پیشنهاد لینک یک صفحه‌ی تأیید در سایت را دارد (REQUESTS_CONFIRM_URL): متقاضی گزینه‌هایی را که می‌خواهد تیک می‌زند، اطلاعات فیلمش را می‌فرستد و شرایط را می‌پذیرد. جوابش خودبه‌خود روی درخواست می‌آید.",
                "ثبت‌نام‌های ایمیلی به انگلیسی و با اطلاعات فیلم نوشته می‌شوند و بعد از اینکه چکشان کردی و «فرستادن» را زدی، از آدرس شرکت برای برگزارکننده می‌روند و متقاضی در رونوشت است.",
                "جواب برگزارکننده‌ها با IMAP از صندوق شرکت خوانده می‌شود (REQUESTS_IMAP_*، فقط خواندن، چیزی خوانده‌شده علامت نمی‌خورد) و زیر هر ثبت‌نام به شکل دریافت شد، پذیرفته شد، پذیرفته نشد یا چیز بیشتری می‌خواهند نشان داده می‌شود، با یک خلاصه‌ی کوتاه و یک یادداشت آماده برای متقاضی.",
                "بدون کلیک تو چیزی برای کسی فرستاده نمی‌شود. ثبت‌نام در سایت‌های دیگر (و FilmFreeway) هنوز دستی است.",
            ],
        },
    },
    {
        "version": "1.9.2",
        "date": "2026-10-12",
        "title": {
            "en": "Clear message when the Google connection expires",
            "fa": "پیام روشن وقتی اتصال گوگل منقضی می‌شود",
        },
        "changes": {
            "en": [
                "When Google rejects the saved login (expired or revoked), the dashboard shows a \"Reconnect Google\" button instead of a raw error.",
                "Reconnecting with the same account keeps all tasks and events.",
            ],
            "fa": [
                "وقتی گوگل ورود ذخیره‌شده را رد کند (منقضی یا لغو شده)، داشبورد به جای خطای خام یک دکمه‌ی «اتصال دوباره‌ی گوگل» نشان می‌دهد.",
                "اتصال دوباره با همان حساب، همه‌ی کارها و رویدادها را نگه می‌دارد.",
            ],
        },
    },
    {
        "version": "1.9.1",
        "date": "2026-10-10",
        "title": {
            "en": "Fresh look and dark mode",
            "fa": "ظاهر تازه و حالت تاریک",
        },
        "changes": {
            "en": [
                "Warmer, calmer colors, softer cards and a tidier header on every page.",
                "Dark mode: the dashboard follows your phone or computer setting.",
                "The language switch is now a small toggle; the selected tab and the open email stand out more.",
            ],
            "fa": [
                "رنگ‌های گرم‌تر و آرام‌تر، کارت‌های نرم‌تر و هدر مرتب‌تر در همه‌ی صفحه‌ها.",
                "حالت تاریک: داشبورد از تنظیم گوشی یا کامپیوترت پیروی می‌کند.",
                "انتخاب زبان حالا یک کلید کوچک است و تب انتخاب‌شده و ایمیل باز بهتر دیده می‌شوند.",
            ],
        },
    },
    {
        "version": "1.9.0",
        "date": "2026-10-10",
        "title": {
            "en": "Review page for the film dashboard",
            "fa": "صفحه‌ی بررسی داشبورد فیلم",
        },
        "changes": {
            "en": [
                "New \"Film dashboard\" page: the funds and events the pipeline found, each with its dates and the exact quotes they came from.",
                "Approve or reject each record, with an optional note. Approving does not publish anything yet; the website sync comes later.",
                "The page appears only when FILMDASH_DATABASE_URL is set in .env (see pipeline/README.md).",
            ],
            "fa": [
                "صفحه‌ی تازه‌ی «داشبورد فیلم»: فاندها و رویدادهایی که پایپ‌لاین پیدا کرده، هر کدام با تاریخ‌ها و نقل‌قول دقیقی که از آن آمده‌اند.",
                "هر رکورد را می‌شود با یک یادداشت اختیاری تأیید یا رد کرد. تأیید هنوز چیزی را در سایت منتشر نمی‌کند؛ همگام‌سازی با سایت بعداً می‌آید.",
                "این صفحه فقط وقتی دیده می‌شود که FILMDASH_DATABASE_URL در .env تنظیم شده باشد (راهنما در pipeline/README.md).",
            ],
        },
    },
    {
        "version": "1.8.1",
        "date": "2026-10-07",
        "title": {
            "en": "Delete straight from the list",
            "fa": "حذف مستقیم از فهرست",
        },
        "changes": {
            "en": [
                "Every email row now shows a small trash icon next to the arrow, so you can delete without opening the row. It still asks you to confirm first.",
            ],
            "fa": [
                "کنار فلش هر ردیف ایمیل حالا یک آیکون سطل زباله هست، تا بدون باز کردن ردیف بتوانی حذفش کنی. باز هم اول تأیید می‌گیرد.",
            ],
        },
    },
    {
        "version": "1.8.0",
        "date": "2026-10-07",
        "title": {
            "en": "Delete emails from the dashboard",
            "fa": "حذف ایمیل‌ها از داشبورد",
        },
        "changes": {
            "en": [
                "Every open row now has a Delete button. It asks you to confirm first, because a deleted email cannot be brought back.",
                "Deleting removes the email, its draft and its suggested events from every tab. Gmail is not touched, and the same email is never read again.",
            ],
            "fa": [
                "هر ردیف باز حالا یک دکمه‌ی «حذف» دارد. اول از تو تأیید می‌گیرد، چون ایمیل حذف‌شده برنمی‌گردد.",
                "حذف، ایمیل و پیش‌نویس و قرارهای پیشنهادی‌اش را از همه‌ی تب‌ها برمی‌دارد. جیمیل دست نمی‌خورد و همان ایمیل دوباره خوانده نمی‌شود.",
            ],
        },
    },
    {
        "version": "1.7.0",
        "date": "2026-10-07",
        "title": {
            "en": "Open emails inline, right in the list",
            "fa": "باز کردن ایمیل‌ها همان‌جا، داخل فهرست",
        },
        "changes": {
            "en": [
                "Every row in every tab is now an accordion: click it to open the details right below it, click again to close. Only one row is open at a time.",
                "Everything you could do on the email page you can now do inside the open row: read the original email, edit, rewrite, save, approve and send or reject the draft, add or dismiss events, mark mail as done, draft a reply anyway, and put a rejected email back.",
                "Actions no longer reload the page. The row updates in place, a small message tells you what happened, and the tab counts change. A row that no longer belongs to its tab (for example after sending) disappears from it.",
                "The details are loaded only when you open a row, so the dashboard opens faster. Text you typed into a draft stays when you close and re-open a row.",
                "The Events tab rows are accordions too, with the editable event card inside.",
                "Links like /#task-123 open that row. Without JavaScript the page still works: a row opens with a normal click and every action returns you to the dashboard with that row open. The old email page /tasks/123 still works as a fallback.",
                "A narrower, single-column layout that fits phones (no sideways scrolling, bigger tap targets) and follows the language direction. English is the default language and the EN | FA choice is remembered.",
            ],
            "fa": [
                "هر ردیف در هر تب حالا آکاردئون است: روی آن کلیک کن تا جزئیاتش درست زیر خودش باز شود و دوباره کلیک کن تا بسته شود. فقط یک ردیف در یک زمان باز است.",
                "هر کاری که در صفحه‌ی جدای ایمیل می‌شد کرد، حالا داخل ردیف باز هم شدنی است: خواندن ایمیل اصلی، ویرایش، بازنویسی، ذخیره، تأیید و ارسال یا رد پیش‌نویس، افزودن یا ردِ قرار، «انجام شد» برای ایمیل‌های بدون جواب، نوشتن جواب به‌هرحال، و برگرداندن ایمیل ردشده.",
                "کارها دیگر صفحه را دوباره بارگذاری نمی‌کنند. ردیف همان‌جا به‌روز می‌شود، یک پیام کوتاه می‌گوید چه شد و شمارنده‌ی تب‌ها عوض می‌شود. ردیفی که دیگر به آن تب تعلق ندارد (مثلاً بعد از ارسال) از آن ناپدید می‌شود.",
                "جزئیات فقط وقتی ردیف را باز می‌کنی بارگذاری می‌شود، پس داشبورد سریع‌تر باز می‌شود. متنی که در پیش‌نویس تایپ کرده‌ای با بستن و دوباره باز کردن ردیف از بین نمی‌رود.",
                "ردیف‌های تب رویدادها هم آکاردئون‌اند و کارت قابل‌ویرایش رویداد داخلشان است.",
                "لینک‌هایی مثل ‎/#task-123‎ همان ردیف را باز می‌کنند. بدون جاوااسکریپت هم صفحه کار می‌کند: ردیف با کلیک معمولی باز می‌شود و هر کار تو را به داشبورد با همان ردیف باز برمی‌گرداند. صفحه‌ی قدیمی ‎/tasks/123‎ هم به‌عنوان جایگزین کار می‌کند.",
                "چیدمان تک‌ستونی و باریک‌تر که روی گوشی جا می‌شود (بدون اسکرول افقی و با دکمه‌های بزرگ‌تر) و با جهت زبان عوض می‌شود. زبان پیش‌فرض انگلیسی است و انتخاب EN | FA به خاطر سپرده می‌شود.",
            ],
        },
    },
    {
        "version": "1.6.0",
        "date": "2026-10-06",
        "title": {
            "en": "Dashboard tabs: Needs reply, Events, Other mail",
            "fa": "تب‌های داشبورد: نیازمند جواب، رویدادها، سایر ایمیل‌ها",
        },
        "changes": {
            "en": [
                "The dashboard now has five tabs with counts: Needs reply, Events, Other mail, Sent and Rejected.",
                "New Events tab: all upcoming events found in any email, sorted by date. Each one is the usual editable card with an end date, location, an \"Open invite link\" button, a link back to its email and calendar conflict warnings. Adding or dismissing an event brings you back to this tab.",
                "New Other mail tab: emails that need no reply, each with its category and a one-line summary. \"Done\" archives it here only (Gmail is not touched), and \"Draft a reply anyway\" writes a draft that still waits for your approval. Archived mail can be shown and moved back.",
                "A failed draft now appears under Needs reply, and the old links to the previous tabs still work.",
                "A calendar invitation is never offered for events that come from newsletters or forwarded emails.",
                "The event cards fit narrow phone screens.",
            ],
            "fa": [
                "داشبورد حالا پنج تب با شمارنده دارد: نیازمند جواب، رویدادها، سایر ایمیل‌ها، ارسال‌شده و ردشده.",
                "تب تازه‌ی رویدادها: همه‌ی رویدادهای آینده که در هر ایمیلی پیدا شده، مرتب‌شده بر اساس تاریخ. هر کدام همان کارت قابل‌ویرایش است با تاریخ پایان، مکان، دکمه‌ی «باز کردن لینک دعوت»، لینک به ایمیل مربوط و هشدار تداخل تقویم. بعد از افزودن یا رد کردن یک رویداد به همین تب برمی‌گردی.",
                "تب تازه‌ی سایر ایمیل‌ها: ایمیل‌هایی که جواب نمی‌خواهند، هرکدام با دسته و خلاصه‌ی یک‌خطی. «انجام شد» فقط همین‌جا بایگانی می‌کند (جیمیل دست‌نخورده می‌ماند) و «با این حال جواب بنویس» پیش‌نویسی می‌نویسد که باز هم منتظر تأیید تو می‌ماند. ایمیل‌های بایگانی‌شده را می‌شود دید و برگرداند.",
                "پیش‌نویس ناموفق حالا زیر «نیازمند جواب» دیده می‌شود و لینک‌های قدیمی تب‌های قبلی هم کار می‌کنند.",
                "برای رویدادهایی که از خبرنامه یا ایمیل فورواردشده آمده‌اند دیگر پیشنهاد دعوت‌نامه‌ی تقویم داده نمی‌شود.",
                "کارت‌های رویداد روی صفحه‌ی باریک موبایل جا می‌شوند.",
            ],
        },
    },
    {
        "version": "1.5.0",
        "date": "2026-10-06",
        "title": {
            "en": "Every email is read, not only the ones that need a reply",
            "fa": "همه‌ی ایمیل‌ها خوانده می‌شوند، نه فقط ایمیل‌هایی که جواب می‌خواهند",
        },
        "changes": {
            "en": [
                "Every new email is now read once by a cheap AI model that sorts it (needs a reply, event invitation, information, newsletter, receipt, other), writes a one-line summary and finds events, deadlines and related events.",
                "A reply is drafted only when a real person is waiting for an answer. Newsletters, automated mail and forwarded messages never get a draft. Emails that need no reply appear under the new \"Other mail\" tab.",
                "Newsletters and automated mail are no longer ignored: they are still read for events and summaries (turn it off with PROCESS_BULK=false). The default Gmail search no longer excludes the Promotions, Updates, Social and Forums tabs.",
                "Better events: multi-day events (end date), the invitation link with an \"Open invite link\" button, cancelled events are shown as cancelled and cannot be added, cleaner titles and descriptions, and conflicting dates or times in one email are flagged.",
                "The same event arriving twice (invitation, reminder, forward) is shown only once, matched by its link or by its title and date.",
                "For forwarded emails the original sender, subject and date are read from inside the message. Other events mentioned only by name are listed without dates.",
                "Cost controls: a per-run limit for emails and a smaller one for bulk mail, a configurable cheap model (CLASSIFY_MODEL) and an optional blocked-senders list (SKIP_SENDERS).",
                "Safety: email text is treated as untrusted data. The AI has no tools, its answers are validated, links are only displayed and never opened, and nothing is sent or added to the calendar without your approval.",
                "The database gains new columns automatically when the app starts. Nothing is deleted.",
            ],
            "fa": [
                "هر ایمیل جدید یک بار توسط یک مدل هوش مصنوعی ارزان خوانده می‌شود: نوع آن (نیازمند جواب، دعوت به رویداد، اطلاع‌رسانی، خبرنامه، رسید، سایر) مشخص می‌شود، یک خلاصه‌ی یک‌خطی نوشته می‌شود و قرارها، مهلت‌ها و رویدادهای مرتبط پیدا می‌شوند.",
                "فقط وقتی یک آدم واقعی منتظر جواب است پیش‌نویس جواب نوشته می‌شود. برای خبرنامه‌ها، ایمیل‌های خودکار و ایمیل‌های فورواردشده هرگز پیش‌نویس نوشته نمی‌شود. ایمیل‌هایی که جواب نمی‌خواهند در بخش تازه‌ی «سایر ایمیل‌ها» دیده می‌شوند.",
                "خبرنامه‌ها و ایمیل‌های خودکار دیگر نادیده گرفته نمی‌شوند: برای پیدا کردن قرار و نوشتن خلاصه خوانده می‌شوند (با PROCESS_BULK=false خاموش می‌شود). جست‌وجوی پیش‌فرض جیمیل هم دیگر دسته‌های Promotions، Updates، Social و Forums را کنار نمی‌گذارد.",
                "قرارهای بهتر: رویداد چندروزه (تاریخ پایان)، لینک دعوت با دکمه‌ی «باز کردن لینک دعوت»، نمایش قرارهای لغوشده (که قابل افزودن نیستند)، عنوان و توضیح تمیزتر، و هشدار وقتی یک ایمیل تاریخ یا ساعت‌های ناسازگار می‌دهد.",
                "اگر یک قرار دو بار برسد (دعوت، یادآوری، فوروارد) فقط یک بار نشان داده می‌شود؛ با لینک یا با عنوان و تاریخ تشخیص داده می‌شود.",
                "برای ایمیل‌های فورواردشده، فرستنده، موضوع و تاریخ اصلی از داخل متن خوانده می‌شود. رویدادهای دیگری که فقط نامشان آمده بدون تاریخ فهرست می‌شوند.",
                "کنترل هزینه: سقف تعداد ایمیل در هر بار بررسی و سقف کمتر برای خبرنامه‌ها، مدل ارزان قابل تنظیم (CLASSIFY_MODEL) و فهرست اختیاری فرستنده‌های نادیده‌گرفته‌شده (SKIP_SENDERS).",
                "امنیت: متن ایمیل داده‌ی غیرقابل‌اعتماد حساب می‌شود. هوش مصنوعی ابزاری ندارد، جواب‌هایش بررسی می‌شود، لینک‌ها فقط نمایش داده می‌شوند و هرگز باز نمی‌شوند، و بدون تأیید تو چیزی ارسال یا به تقویم اضافه نمی‌شود.",
                "ستون‌های تازه‌ی دیتابیس هنگام شروع برنامه خودکار اضافه می‌شوند. چیزی پاک نمی‌شود.",
            ],
        },
    },
    {
        "version": "1.4.0",
        "date": "2026-10-06",
        "title": {
            "en": "English and Persian interface",
            "fa": "رابط دوزبانه: انگلیسی و فارسی",
        },
        "changes": {
            "en": [
                "The whole interface now exists in English and Persian. Switch language from the header; your choice is remembered.",
                "English is now the default language (set DEFAULT_LANGUAGE=fa in .env to keep Persian as the default).",
                "New Settings page for the app language and your time zone (no longer fixed to Europe/Berlin).",
                "Event warnings (unclear date format, missing year, guessed time zone, ...) are now translated automatically instead of being stored in one language.",
                "The page direction (left-to-right or right-to-left) follows the language; times, dates, emails and links always stay left-to-right.",
            ],
            "fa": [
                "کل رابط کاربری حالا انگلیسی و فارسی دارد. زبان را از بالای صفحه عوض کن؛ انتخابت یادآوری می‌شود.",
                "زبان پیش‌فرض حالا انگلیسی است (برای فارسی به‌عنوان پیش‌فرض، DEFAULT_LANGUAGE=fa را در .env بگذار).",
                "صفحه‌ی تنظیمات برای زبان برنامه و منطقه‌ی زمانی اضافه شد (دیگر ثابت روی Europe/Berlin نیست).",
                "هشدارهای قرارها (قالب نامشخص تاریخ، نبودن سال، منطقه‌ی زمانی حدسی و ...) حالا خودکار ترجمه می‌شوند.",
                "جهت صفحه با زبان عوض می‌شود؛ ساعت‌ها، تاریخ‌ها، ایمیل‌ها و لینک‌ها همیشه چپ‌به‌راست می‌مانند.",
            ],
        },
    },
    {
        "version": "1.3.1",
        "date": "2026-10-04",
        "title": {"en": "Time display fix", "fa": "اصلاح نمایش ساعت"},
        "changes": {
            "en": [
                "Times on event cards are no longer shown reversed (for example 30:10 instead of 10:30).",
                "The \"please check\" note appears only for an unclear date, time or time zone, and is written in Persian.",
            ],
            "fa": [
                "ساعت‌ها در کارت قرار دیگر برعکس نمایش داده نمی‌شوند (مثلاً ۳۰:۱۰ به‌جای ۱۰:۳۰).",
                "یادداشت «لطفاً چک کن» فقط برای ابهام در تاریخ، ساعت یا منطقه‌ی زمانی و به فارسی نوشته می‌شود.",
            ],
        },
    },
    {
        "version": "1.3.0",
        "date": "2026-10-04",
        "title": {"en": "Version number and changelog", "fa": "شماره‌ی نسخه و تاریخچه‌ی تغییرات"},
        "changes": {
            "en": [
                "The version number is shown at the bottom of every page.",
                "A Changelog page was added to see the features of each version.",
            ],
            "fa": [
                "شماره‌ی نسخه پایین همه‌ی صفحه‌ها نمایش داده می‌شود.",
                "صفحه‌ی «تاریخچه‌ی تغییرات» برای دیدن قابلیت‌های هر نسخه اضافه شد.",
            ],
        },
    },
    {
        "version": "1.2.0",
        "date": "2026-10-04",
        "title": {"en": "Google Calendar connection", "fa": "اتصال به تقویم گوگل"},
        "changes": {
            "en": [
                "The next 7 days of your calendar are shown at the top of the dashboard.",
                "Meetings in received emails and in your sent replies are found automatically, with an \"Add to calendar\" button.",
                "The time zone of a meeting is detected from its place, with a warning when it differs from your local time.",
                "A conflict warning appears when a meeting overlaps another event in your calendar.",
                "You can send a calendar invitation to the other person.",
                "An \"Event\" tag appears next to emails that contain meetings.",
                "Dates are shown in your local time, not server time.",
            ],
            "fa": [
                "نمایش برنامه‌های ۷ روز آینده‌ی تقویم بالای داشبورد.",
                "پیدا کردن خودکار قرارها در ایمیل‌های دریافتی و جواب‌های ارسالی، با دکمه‌ی «افزودن به تقویم».",
                "تشخیص منطقه‌ی زمانی قرار از روی مکان و هشدار وقتی با وقت محلی فرق دارد.",
                "هشدار تداخل وقتی زمان قرار با برنامه‌ی دیگری در تقویم هم‌زمان است.",
                "امکان فرستادن دعوت‌نامه‌ی تقویم برای طرف مقابل.",
                "برچسب «قرار» کنار ایمیل‌هایی که قرار دارند.",
                "تاریخ‌ها به وقت محلی تو نمایش داده می‌شوند، نه وقت سرور.",
            ],
        },
    },
    {
        "version": "1.1.0",
        "date": "2026-10-03",
        "title": {"en": "Changing the Gmail account", "fa": "تغییر حساب جیمیل"},
        "changes": {
            "en": ["A \"Change account\" button to switch between the test mailbox and the main mailbox."],
            "fa": ["دکمه‌ی «تغییر حساب» برای جابه‌جا شدن بین ایمیل آزمایشی و ایمیل اصلی."],
        },
    },
    {
        "version": "1.0.0",
        "date": "2026-10-03",
        "title": {"en": "First version", "fa": "نسخه‌ی اول"},
        "changes": {
            "en": [
                "New Gmail messages are read automatically; newsletters and automated mail are skipped.",
                "Reply drafts are written with Claude, in the sender's own language.",
                "A task queue to review, edit, rewrite, reject, or approve and send each reply.",
                "Replies are sent in the same email thread, never automatically.",
            ],
            "fa": [
                "خواندن خودکار ایمیل‌های جدید جیمیل و کنار گذاشتن خبرنامه‌ها و ایمیل‌های خودکار.",
                "نوشتن پیش‌نویس جواب با Claude، به زبان خود فرستنده.",
                "صف تسک‌ها برای بررسی، ویرایش، بازنویسی، رد یا تأیید و ارسال هر جواب.",
                "ارسال جواب در همان رشته‌ی ایمیل، بدون ارسال خودکار.",
            ],
        },
    },
]
