#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, ConversationHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation handler
QUESTION, ANSWER, DIFFICULTY = range(3)

# User session state
# Note: keeping simple in-memory dicts keyed by user_id. For production, consider persistence.
user_scores = {}
user_difficulty = {}
user_question_list = {}   # user_id -> list of 10 questions prepared for the session
user_question_index = {}  # user_id -> current index in the prepared list (0..9)

# Load quiz questions
def load_questions():
    if os.path.exists('questions.json'):
        with open('questions.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    else:
        # Default questions if file doesn't exist
        return []

# Quiz questions
questions = load_questions()

def start(update: Update, context: CallbackContext) -> int:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    update.message.reply_text(
        f'Привет, {user.first_name}! Добро пожаловать в квиз по вселенной "Ведьмак" Анджея Сапковского.\n\n'
        f'Для начала квиза введите команду /quiz\n'
        f'Для выбора сложности вопросов введите /difficulty\n'
        f'Для просмотра правил введите /help\n'
        f'Для просмотра вашего счета введите /score'
    )
    # Также сразу покажем правила квиза
    help_command(update, context)
    return ConversationHandler.END

def _build_all_levels_plan() -> list:
    """Build a 10-question plan with equal distribution across difficulties 1..5.
    Attempts to select 2 questions per difficulty. If some levels have fewer than 2,
    the remaining slots are filled from other levels with available questions.
    """
    # Group questions by difficulty (default to 3)
    groups = {lvl: [] for lvl in range(1, 6)}
    for q in questions:
        lvl = q.get('difficulty', 3)
        if lvl in groups:
            groups[lvl].append(q)

    plan = []
    # First pass: try to take up to 2 from each level
    for lvl in range(1, 6):
        pool = groups[lvl][:]
        random.shuffle(pool)
        take = min(2, len(pool))
        plan.extend(pool[:take])

    # If less than 10 collected, fill from remaining pools
    if len(plan) < 10:
        remaining = []
        for lvl in range(1, 6):
            pool = groups[lvl][:]
            random.shuffle(pool)
            remaining.extend(pool)
        # Remove already selected objects by identity
        # Using id() as questions are dicts loaded from a shared list
        selected_ids = {id(q) for q in plan}
        remaining = [q for q in remaining if id(q) not in selected_ids]
        random.shuffle(remaining)
        need = 10 - len(plan)
        plan.extend(remaining[:need])

    # If still less than 10 (not enough total questions), just return what we have
    # Shuffle final plan for mixing
    random.shuffle(plan)
    return plan[:10]

def _build_single_level_plan(level: int) -> list:
    """Build a 10-question plan for a single difficulty level. If fewer than 10
    available, use all available (quiz will end early)."""
    pool = [q for q in questions if q.get('difficulty', 3) == level]
    random.shuffle(pool)
    return pool[:10]

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text(
        'Правила квиза:\n\n'
        '1. Вам будут предложены вопросы о вселенной "Ведьмак"\n'
        '2. Для каждого вопроса есть несколько вариантов ответа\n'
        '3. Выберите правильный ответ, нажав на соответствующую кнопку\n'
        '4. За каждый правильный ответ вы получаете 1 очко\n'
        '5. Вы можете выбрать уровень сложности вопросов от 1 (самый простой) до 5 (самый сложный)\n'
        '6. Каждый квиз состоит из 10 вопросов. В конце показывается итоговый результат.\n\n'
        'Команды:\n'
        '/start - Начать бота\n'
        '/quiz - Начать новый квиз\n'
        '/difficulty - Выбрать уровень сложности\n'
        '/score - Показать ваш текущий счет\n'
        '/help - Показать эту справку'
    )

def score(update: Update, context: CallbackContext) -> None:
    """Show user's score."""
    user_id = update.effective_user.id
    if user_id in user_scores:
        difficulty_level = user_difficulty.get(user_id, 'не выбран')
        update.message.reply_text(f'Ваш текущий счет: {user_scores[user_id]}\nТекущий уровень сложности: {difficulty_level}')
    else:
        update.message.reply_text('Вы еще не участвовали в квизе. Введите /quiz для начала.')

def set_difficulty(update: Update, context: CallbackContext) -> int:
    """Set the difficulty level for questions."""
    keyboard = [
        [InlineKeyboardButton("1 - Самый простой", callback_data="1")],
        [InlineKeyboardButton("2 - Легкий", callback_data="2")],
        [InlineKeyboardButton("3 - Средний", callback_data="3")],
        [InlineKeyboardButton("4 - Сложный", callback_data="4")],
        [InlineKeyboardButton("5 - Эксперт", callback_data="5")],
        [InlineKeyboardButton("Все уровни", callback_data="0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        'Выберите уровень сложности вопросов:', 
        reply_markup=reply_markup
    )
    return DIFFICULTY

def handle_difficulty(update: Update, context: CallbackContext) -> int:
    """Handle the user's difficulty selection."""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    difficulty = int(query.data)
    
    if difficulty == 0:
        user_difficulty[user_id] = "Все уровни"
        query.edit_message_text(f"Установлен уровень сложности: Все уровни\nДля начала квиза введите /quiz")
    else:
        user_difficulty[user_id] = difficulty
        query.edit_message_text(f"Установлен уровень сложности: {difficulty}\nДля начала квиза введите /quiz")
    
    return ConversationHandler.END

def quiz(update: Update, context: CallbackContext) -> int:
    """Start the quiz."""
    user_id = update.effective_user.id
    
    # Initialize score if user is new
    if user_id not in user_scores:
        user_scores[user_id] = 0
    
    # Set default difficulty if not set
    if user_id not in user_difficulty:
        user_difficulty[user_id] = "Все уровни"
    
    # Check if we have questions
    if not questions:
        update.message.reply_text('К сожалению, вопросы еще не загружены. Попробуйте позже.')
        return ConversationHandler.END
    
    # Prepare a session plan if not exists or finished
    plan = user_question_list.get(user_id)
    idx = user_question_index.get(user_id, 0)

    if not plan or idx >= len(plan):
        # New session => reset score and (re)build plan
        user_scores[user_id] = 0
        difficulty = user_difficulty[user_id]
        if difficulty == "Все уровни":
            plan = _build_all_levels_plan()
        else:
            plan = _build_single_level_plan(difficulty)

        if not plan:
            if difficulty == "Все уровни":
                update.message.reply_text('Нет доступных вопросов для квиза. Пожалуйста, попробуйте позже.')
            else:
                update.message.reply_text(
                    f'Нет вопросов для уровня сложности {difficulty}. '
                    f'Пожалуйста, выберите другой уровень сложности с помощью /difficulty'
                )
            return ConversationHandler.END

        user_question_list[user_id] = plan
        user_question_index[user_id] = 0
        idx = 0

    # Fetch next question in the plan
    question = plan[idx]
    context.user_data['current_question'] = question
    
    # Create keyboard with answer options
    keyboard = []
    for option in question['options']:
        keyboard.append([InlineKeyboardButton(option, callback_data=option)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    difficulty_text = f"Сложность: {question.get('difficulty', 'не указана')}/5"
    progress_text = f"Вопрос {idx + 1} из {len(plan)}"
    
    # Send question
    update.message.reply_text(
        f"{progress_text}\nВопрос: {question['question']}\n\n{difficulty_text}", 
        reply_markup=reply_markup
    )
    
    return QUESTION

def handle_answer(update: Update, context: CallbackContext) -> int:
    """Handle the user's answer."""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    question = context.user_data.get('current_question')
    user_answer = query.data
    
    if not question:
        query.edit_message_text('Произошла ошибка. Пожалуйста, начните квиз заново с помощью /quiz')
        return ConversationHandler.END
    
    # Check if the answer is correct
    if user_answer == question['correct_answer']:
        user_scores[user_id] = user_scores.get(user_id, 0) + 1
        query.edit_message_text(
            f"✅ Правильно! {question.get('explanation', '')}\n\n"
            f"Ваш текущий счет: {user_scores[user_id]}\n\n"
            f"Для продолжения введите /quiz"
        )
    else:
        query.edit_message_text(
            f"❌ Неправильно. Правильный ответ: {question['correct_answer']}\n"
            f"{question.get('explanation', '')}\n\n"
            f"Ваш текущий счет: {user_scores[user_id]}\n\n"
            f"Для продолжения введите /quiz"
        )
    
    # Advance index and check for session end
    try:
        user_question_index[user_id] = user_question_index.get(user_id, 0) + 1
        idx = user_question_index[user_id]
        plan = user_question_list.get(user_id, [])
        if idx >= len(plan):
            # Session finished
            final_score = user_scores.get(user_id, 0)
            total = len(plan) if plan else 10
            query.message.reply_text(
                f"🏁 Квиз завершен! Ваш результат: {final_score} из {total}.\n"
                f"Чтобы начать заново, введите /quiz или смените сложность через /difficulty."
            )
            # Reset session plan/index; keep difficulty
            user_question_list[user_id] = []
            user_question_index[user_id] = 0
    except Exception as e:
        logger.exception("Ошибка при завершении сессии: %s", e)

    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel and end the conversation."""
    update.message.reply_text('Квиз отменен. Для начала нового квиза введите /quiz')
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error('Переменная окружения TELEGRAM_BOT_TOKEN не установлена.')
        raise RuntimeError('TELEGRAM_BOT_TOKEN must be set in the environment')
    updater = Updater(token=token)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add conversation handler for quiz
    quiz_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('quiz', quiz)],
        states={
            QUESTION: [CallbackQueryHandler(handle_answer)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Add conversation handler for difficulty selection
    difficulty_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('difficulty', set_difficulty)],
        states={
            DIFFICULTY: [CallbackQueryHandler(handle_difficulty)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("score", score))
    dispatcher.add_handler(quiz_conv_handler)
    dispatcher.add_handler(difficulty_conv_handler)

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
