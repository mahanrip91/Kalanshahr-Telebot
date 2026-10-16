"""
ابزار مشترک: خیلی از ورودی‌های ربات (مبلغ، شماره حساب، اسم و...) باید حتماً
با ریپلای روی همون پیامی که بات پرسیده وارد بشن - نه هر پیام ولِ دیگه‌ای.
این کار مخصوصاً تو گروه‌های شلوغ جلوی قاطی شدن ورودی‌های چند نفر رو می‌گیره.

استثنا: دکمه‌های اصلی منو (کار، بانک، کازینو و...) نیازی به ریپلای ندارن،
چون درخواست مستقل هستن نه ادامه‌ی یه مکالمه‌ی چندمرحله‌ای.
"""
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


async def set_prompt(state: FSMContext, message_id: int, **extra):
    """آیدی پیام سوال بات رو تو FSM ذخیره می‌کنه تا بعداً ریپلای روش چک بشه"""
    await state.update_data(prompt_id=message_id, **extra)


async def check_reply(message: Message, state: FSMContext) -> bool:
    """
    True اگه کاربر درست رو پیام بات ریپلای کرده باشه.
    اگه نه، هیچی نمیگه (سکوت) و False برمیگردونه - کاربر هر وقت خواست میتونه درست ریپلای کنه.
    """
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    if not prompt_id or not message.reply_to_message or message.reply_to_message.message_id != prompt_id:
        return False
    return True
