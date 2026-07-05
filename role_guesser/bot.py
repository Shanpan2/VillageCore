from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


ROLE_GUESSER_TOKEN = os.getenv("ROLE_GUESSER_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATA_PATH = Path(__file__).with_name("data") / "roles.csv"
INTRO_QUIZ_DATA_PATH = Path(__file__).with_name("data") / "intro_quiz.json"


def parse_discord_id(value: str | None, name: str) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value.isdigit():
        print(
            f"⚠️ {name} must be a numeric Discord ID, not an invite URL or text: {value!r}",
            flush=True,
        )
        return None
    return int(value)


TARGET_GUILD_ID = parse_discord_id(GUILD_ID, "GUILD_ID")

MOD_ALIASES = {
    "vanilla": "Vanilla",
    "among us": "Vanilla",
    "amongus": "Vanilla",
    "バニラ": "Vanilla",
    "town of host": "TOH",
    "toh": "TOH",
    "tohk": "TOHK",
    "supernewroles": "SNR",
    "super new roles": "SNR",
    "snr": "SNR",
    "extremeroles": "ExR",
    "extreme roles": "ExR",
    "exr": "ExR",
    "torgmia": "TORGMIA",
    "nos": "NOS",
}

FEATURE_QUESTIONS = {
    "team_crewmate": "その役職はクルー陣営ですか？",
    "team_impostor": "その役職はインポスター陣営ですか？",
    "team_neutral": "その役職は第三陣営ですか？",
    "team_liberal": "リベラル陣営ですか？（リーダー/ドーヴ/ミリタントで資金を貯めて勝つ第四陣営）",
    "team_madmate": "マッドメイト陣営・狂人系チームですか？",
    "team_jackal": "ジャッカル陣営ですか？",
    "modifier_role": "メイン役職に追加で付く属性・モディファイアですか？",
    "nos_role": "NoS / Nebula on the Ship側にもある役職/仕様ですか？",
    "snr_role": "SuperNewRoles側にもある役職/仕様ですか？",
    "tohk_role": "TownOfHost-K側にもある役職/仕様ですか？",
    "exr_role": "Extreme Roles側にもある役職/仕様ですか？",
    "nos_modifier_role": "NoSのモディファイア役職ですか？",
    "buff_modifier_power": "移動速度・投票数・キル性能などを強化するバフ属性ですか？",
    "debuff_modifier_power": "視界低下・投票不可・機器使用不可などのデバフ属性ですか？",
    "evil_support_power": "マッドメイトやジャッカルフレンズなど、別陣営を助ける補助・狂人系役職ですか？",
    "host_observer_power": "ホスト専用の観戦・GM系役職ですか？",
    "host_only_power": "必ずホストに割り当てられる役職ですか？",
    "non_counting_power": "生存者数や役職数のカウントに含まれませんか？",
    "plain_role_power": "特殊能力はほぼなく、共通設定や視界だけが変わる役職ですか？",
    "emergency_repair_power": "サボタージュを即座に修理する能力がありますか？",
    "no_task_role": "タスクを持たない役職ですか？",
    "utility_restriction_power": "アドミン・バイタル・カメラ・緊急会議などの機器使用が制限されますか？",
    "sabotage_repair_restriction_power": "特定のサボタージュ修理ができない役職/属性ですか？",
    "limited_kill_power": "キル可能回数に上限がありますか？",
    "task_kill_charge_power": "タスク進捗でキル回数やキルCTが変わりますか？",
    "can_kill": "自分の操作で誰かを死亡させる能力がありますか？",
    "normal_kill": "普通のキルボタンでキルする役職ですか？",
    "sheriff_misfire_power": "キル不可対象を撃つと、誤爆として自分が死亡する役職ですか？",
    "guess_misfire_power": "会議中の役職推測を外すと、自分が死亡しますか？",
    "suicide_button_power": "自分から自決するボタンや能力を持ちますか？",
    "serial_suicide_timer_power": "キル後、一定時間以内に次のキルをしないと自殺しますか？",
    "gamble_cooldown_power": "キル後の成功/失敗判定で次のキルクールが変わりますか？",
    "target_mismatch_suicide_power": "能力対象の陣営や条件を間違えると自分が死亡しますか？",
    "special_kill": "普通のキルボタン以外で死亡させる能力がありますか？（例: 爆破、推測、ビーム、罠、会議キル）",
    "trap_place_power": "マップ上に罠やトラップを設置できますか？",
    "kill_trap_power": "設置した罠で相手を拘束したりキルしたりできますか？",
    "notify_trap_power": "設置した罠を踏んだ相手の位置や通過を通知できますか？",
    "vent_trap_power": "\u30d9\u30f3\u30c8\u306b\u7f60\u3092\u4ed5\u639b\u3051\u3066\u3001\u4f7f\u7528\u3057\u305f\u30d7\u30ec\u30a4\u30e4\u30fc\u3092\u62d8\u675f\u3067\u304d\u307e\u3059\u304b\uff1f",
    "target_power": "特定の相手を選ぶ能力ですか？（例: 指名、恋人化、投獄、ターゲット指定）",
    "target_kill_power": "特定の相手を殺す/死なせることが目的や能力条件ですか？（例: 賞金首、復讐対象、推測キル）",
    "guard_piercing_power": "ガードやシールドを貫通するキル能力がありますか？",
    "kill_range_modifier_power": "キル可能距離を変更する役職・属性ですか？",
    "kill_power_boost_power": "通常キルの威力やガード貫通力を上げますか？",
    "wave_cannon_power": "波動砲・レーザー・ビームのような直線攻撃ですか？",
    "area_instant_kill_power": "近くにいる複数人を一度にキルできる必殺技がありますか？",
    "projectile_barrage_power": "扇状の弾幕や弾を発射してキルする能力ですか？",
    "multi_hit_kill_power": "設定された必要ヒット数に到達したプレイヤーをキルしますか？",
    "friendly_fire_option_power": "設定により味方にも能力が当たりますか？",
    "uses_vent": "その役職はベントを使えますか？",
    "can_win_alone": "その役職は単独勝利できますか？",
    "additional_win": "他陣営の勝利に便乗して追加勝利しますか？",
    "extra_win_condition_power": "通常の勝利条件に追加条件や勝利阻害条件が付きますか？",
    "can_protect": "誰かを守る能力がありますか？（例: ガード、バリア、キル防止）",
    "can_investigate": "情報を調べる能力がありますか？（例: 役職/陣営/死因/位置を調査）",
    "portable_security_power": "どこでもセキュリティカメラやドアログを見られますか？",
    "portable_admin_power": "どこでもアドミン情報を見られますか？",
    "portable_vitals_power": "どこでもバイタルを確認できますか？",
    "death_cause_power": "死亡したプレイヤーの死因が分かりますか？",
    "task_delegation_power": "他人のタスクを肩代わり・取得できますか？",
    "kill_notification_power": "キル発生時に時間・方角・部屋などの通知を受けますか？",
    "kill_flash_power": "誰かが死亡した瞬間に画面発光などのキルフラッシュを受けますか？",
    "time_rewind_power": "キルを無効化して時間や移動を巻き戻しますか？",
    "guard_sacrifice_power": "他人を守るために自分が身代わりで死亡しますか？",
    "counter_power": "攻撃を防いで反撃や一時的なキル権を得ますか？",
    "body_curse_power": "死体に使ってキラーにクールペナルティ等を与えますか？",
    "camera_install_power": "カメラや監視装置を設置できますか？",
    "vent_usage_analysis_power": "\u30d9\u30f3\u30c8\u3092\u5206\u6790\u3057\u3066\u3001\u524d\u30bf\u30fc\u30f3\u306e\u4f7f\u7528\u60c5\u5831\u3092\u5f97\u3089\u308c\u307e\u3059\u304b\uff1f",
    "lantern_place_light_power": "\u30e9\u30f3\u30bf\u30f3\u3084\u706f\u308a\u3092\u8a2d\u7f6e\u3057\u3066\u3001\u5468\u56f2\u3092\u7167\u3089\u3059\u3053\u3068\u304c\u3067\u304d\u307e\u3059\u304b\uff1f",
    "drone_control_power": "\u30c9\u30ed\u30fc\u30f3\u3092\u547c\u3073\u51fa\u3057\u3066\u8996\u70b9\u3092\u64cd\u4f5c\u3067\u304d\u307e\u3059\u304b\uff1f",
    "drone_task_reveal_power": "\u30c9\u30ed\u30fc\u30f3\u306e\u8fd1\u304f\u3092\u901a\u3063\u305f\u30d7\u30ec\u30a4\u30e4\u30fc\u306e\u30bf\u30b9\u30af\u60c5\u5831\u3092\u78ba\u8a8d\u3067\u304d\u307e\u3059\u304b\uff1f",
    "vent_block_power": "ベントを封鎖・使用不能にできますか？",
    "survival_requirement_power": "生存やタスク進捗が自分の勝利に影響しますか？",
    "photo_power": "写真や記録として位置情報を後で確認できますか？",
    "random_teleport_power": "対象をランダムな場所や別プレイヤーの位置へ飛ばしますか？",
    "mass_teleport_power": "生存者全員を誰かの位置へ集合テレポートさせますか？",
    "teleport_kill_swap_power": "対象と位置を入れ替えながら、その対象をキルできますか？",
    "self_resurrection_power": "自分が死んだ後に復活できますか？",
    "variable_vote_power": "自分の投票数がランダムや設定値で変動しますか？",
    "portal_power": "2点間を移動できるポータルを設置しますか？",
    "meeting_time_power": "会議時間を延長・変更できますか？",
    "noncrew_count_power": "クルー陣営以外の生存者数や役職を報告できますか？",
    "forced_report_power": "キルされると強制的に通報させますか？",
    "jail_power": "対象を投獄して別役職へ変更しますか？",
    "summon_power": "マーキングした相手や死体を自分の位置に呼び寄せますか？",
    "exorcism_power": "死体に悪魔祓い等を行い、情報公開や通報に繋げますか？",
    "stress_power": "近くに人がいるとストレス等が増えて死亡しますか？",
    "exile_resurrection_power": "追放された後に復活や特殊会議が発生しますか？",
    "echo_scan_power": "範囲内のプレイヤーや死体をスキャンで検知しますか？",
    "action_detection_power": "ボタン能力・サボタージュ・ベント使用などの行動を監視・検知しますか？",
    "compare_power": "複数人を比較して判定しますか？（例: 同陣営か、関係があるか）",
    "meeting_ability": "会議中に使う能力がありますか？（例: 推測、追加投票、投票操作、会議中の調査）",
    "meeting_message": "会議中や会議後に専用メッセージが出ますか？（例: パン屋通知、生存通知、能力報告）",
    "has_tasks": "その役職にはタスクがありますか？",
    "task_based_power": "タスク進行で能力・勝利条件・覚醒が変わりますか？",
    "task_progress_display_power": "タスク進捗を名前横や会議中に表示できますか？",
    "extra_task_power": "追加タスクや専用タスクが割り当てられますか？",
    "death_trigger": "自分や対象が死亡した時に能力が発動しますか？（例: 道連れ、後追い、通知、変化）",
    "blood_trail_power": "自分をキルした相手に足跡などの痕跡を残しますか？",
    "scheduled_death": "決まった条件やタイミングで自動的に死亡しますか？",
    "ghost_role": "死亡後・幽霊状態で使う役職ですか？",
    "nos_ghost_role": "NoSの幽霊役職ですか？",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わる能力がありますか？（例: 霊視、蘇生、幽霊能力）",
    "soul_vision_power": "死亡位置に残る霊魂や幽霊を見ることができますか？",
    "ghost_crewmate_power": "ゴーストクルー役職ですか？",
    "ghost_impostor_power": "ゴーストインポスター役職ですか？",
    "ghost_neutral_power": "ゴーストニュートラル役職ですか？",
    "ghost_body_move_power": "幽霊状態で死体を動かせますか？",
    "ghost_sabotage_repair_power": "幽霊状態でサボタージュ修理画面を開けますか？",
    "ghost_photo_power": "幽霊状態で写真を撮って会議に共有しますか？",
    "vent_open_power": "ベントを開閉して動かせますか？",
    "sabotage_cooldown_reset_power": "サボタージュのクールタイムを回復・短縮できますか？",
    "ghost_lights_power": "幽霊状態で特殊な停電を起こせますか？",
    "ghost_dummy_power": "幽霊状態でプレイヤーのダミーを表示できますか？",
    "leak_position_power": "特定プレイヤーの位置を親役職や味方にリークできますか？",
    "ghost_obstacle_power": "幽霊や障害物を出して生存者の移動を妨害しますか？",
    "controllable_illusion_power": "操作できる幻像を出して生存者を混乱させますか？",
    "ghost_stare_win_power": "生存者の近くで動かず佇むことが勝利条件ですか？",
    "ghost_light_power": "幽霊状態で光をともして視界情報を増やしますか？",
    "corpse_pull_power": "死体を自分の位置へ引き寄せますか？",
    "ghost_alert_power": "幽霊状態で任意の場所にアラート音を鳴らしますか？",
    "corpse_duplicate_power": "死体を複製して別の場所に設置できますか？",
    "ghost_possession_vision_power": "幽霊状態で生存者に憑依し、その人の視界を変えますか？",
    "guardian_angel_judgement_power": "守護天使判定、または守護能力を使う幽霊役職ですか？",
    "ghost_meeting_button_power": "幽霊状態で緊急会議を起こせますか？",
    "ghost_noise_mark_power": "幽霊状態で対象にノイズメーカーのような死亡時アラートを付与しますか？",
    "ghost_cooldown_reset_power": "幽霊状態で対象のキルクールや能力クールをリセットしますか？",
    "ghost_role_reveal_power": "幽霊状態で対象の役職を会議で公開できますか？",
    "demon_tracking_power": "死亡したマッドメイト系で、対象位置をインポスターへ通知しますか？",
    "demon_device_disable_power": "死亡したマッドメイト系で、生存者の情報機器を妨害しますか？",
    "demon_vent_open_power": "死亡したマッドメイト系で、対象近くのベントを開けますか？",
    "demon_sabotage_power": "死亡したマッドメイト系で、サボタージュを使えるようになりますか？",
    "assisting_angel_power": "最初に選んだ生存者を支援し、その人の勝利に乗る幽霊役職ですか？",
    "vote_power": "投票や会議結果に直接影響しますか？（例: 追加票、票を減らす、同数処理、強制追放）",
    "exile_win": "会議で追放されることが勝利条件ですか？",
    "tracking_power": "誰かの位置や死体位置を矢印・通知などで追えますか？",
    "role_info_power": "他人の役職や陣営を知る能力がありますか？",
    "omniscient_power": "全員の役職を常に見ることができますか？（例: 神の権能）",
    "public_identity": "自分の役職や存在が他のプレイヤーに分かりますか？",
    "star_visual_power": "スター系のように、名前色・画面発光・色変化などで目立つ役職ですか？",
    "cursor_reveal_power": "会議中のカーソル位置など、操作情報が他人に見えますか？",
    "fake_identity": "他人から別陣営・別役職・別人のように見える能力ですか？",
    "dummy_power": "ダミーや分身を表示する能力がありますか？",
    "body_info_power": "死体・死因・死亡位置に関する情報を得られますか？",
    "corpse_psychometry_power": "\u6b7b\u4f53\u3092\u8aad\u307f\u53d6\u3063\u3066\u3001\u6b7b\u56e0\u30fb\u6b7b\u4ea1\u6642\u523b\u30fb\u72af\u4eba\u306e\u8db3\u8de1\u306a\u3069\u3092\u8abf\u3079\u3089\u308c\u307e\u3059\u304b\uff1f",
    "body_clear_power": "死体を消したり処理したりできますか？（例: 食べる、掃除、蘇生用に消す）",
    "body_move_power": "死体を運んだり別の場所へ動かしたりできますか？",
    "corpse_consumption_power": "死体を食べる・消すことで勝利や能力に関わりますか？",
    "delayed_kill": "能力を使ってから遅れて死亡しますか？（例: 呪い、時限爆弾、後で発動するキル）",
    "vampire_bite_power": "吸血などで対象を遅れて死亡させますか？",
    "blood_stain_power": "次ターンにキル地点から死亡地点まで血痕が残りますか？",
    "thrall_creation_power": "設定により対象の役職を眷属に変更できますか？",
    "collision_kill_power": "一定時間後、すれ違った相手を接触でキルできますか？",
    "bomb_power": "爆弾を付与・設置して爆発させる能力ですか？",
    "marker_power": "マーカーや地点を指定して範囲を作る能力ですか？",
    "disguise_or_invisible": "変身・透明化・姿の偽装ができますか？",
    "invisibility_power": "自分自身が透明化して姿を隠せますか？",
    "shapeshift_power": "他プレイヤーの姿に変身できますか？",
    "global_camouflage_power": "全員の見た目や名前をまとめて隠すカモフラージュ能力ですか？",
    "growth_size_power": "時間経過でプレイヤーの見た目の大きさが変わりますか？",
    "appearance_shuffle_power": "他人の見た目や姿がシャッフルされて視認情報が乱れますか？",
    "area_effect": "周囲や部屋全体に影響しますか？（例: 範囲キル、爆発、全員の移動制限）",
    "sabotage_power": "サボタージュに関わる特別な能力がありますか？（例: 独自サボ、即修理、サボクール操作）",
    "lights_sabotage_power": "停電サボタージュに特化した能力や制限がありますか？",
    "critical_sabotage_power": "リアクター・O2などの緊急サボタージュに特化した能力や制限がありますか？",
    "door_power": "ドアを開閉・一括開放・妨害する能力がありますか？",
    "room_door_open_power": "ドアを開けると同じ部屋のドアもまとめて開きますか？",
    "specific_door_power": "特定の場所や設備のドアだけに作用しますか？（例: トイレ、特定部屋）",
    "revenge_kill": "自分を殺した相手を道連れにできますか？",
    "suicide_risk": "能力の代償や条件で自滅する可能性がありますか？",
    "conversion_power": "他人の役職・陣営・状態を変えますか？（例: サイドキック化、感染、投獄、蘇生）",
    "appoint_power": "対象をシェリフなどの特定役職に任命・転職させますか？",
    "infection_power": "感染や拡散で他人の状態を広げますか？",
    "partner_power": "特定の相方・主人・対象とペアやチームになりますか？",
    "trilemma_power": "3人組の関係になり、他の2人の生死が勝利に影響しますか？",
    "lovers_power": "ラバーズや恋人関係を作ったり狙ったりしますか？",
    "lovers_attribute_power": "他の役職と重複して付くラバーズ属性ですか？",
    "alignment_shift_power": "自分の陣営や勝利条件が途中で変わりますか？",
    "control_power": "他人の移動や行動を直接操作できますか？",
    "restriction_power": "他人の行動や移動を制限しますか？（例: 動けない、通報不可、能力不可、スキップ不可）",
    "ranged_power": "離れた場所から能力やキルを使えますか？（例: 狙撃、投擲、ビーム）",
    "wall_piercing_power": "壁や障害物越しに能力やキルを通せますか？",
    "teleport_power": "テレポートや位置入れ替えに関わる能力ですか？",
    "cooldown_power": "キルクールや能力クールタイムを変化させますか？",
    "speed_power": "移動速度を変化させますか？",
    "movement_power": "移動方法・移動方向・足場や乗り物の動きに干渉しますか？",
    "stationary_death_power": "一定時間止まっていると死亡しますか？",
    "environmental_death_power": "ドア・ベント・はしご・サボタージュなど環境要因で死亡しますか？",
    "report_power": "死体通報や緊急会議ボタンに干渉しますか？（例: 通報不可、強制会議、ポータブルボタン）",
    "vision_power": "視界を広げたり暗くしたりしますか？",
    "vision_debuff_power": "視界が通常より狭くなるデバフ属性ですか？",
    "swap_power": "投票先・位置・役職などを入れ替えますか？",
    "fate_swap_power": "会議中に2人を選び、会議後に役職や票などを入れ替えますか？",
    "dance_power": "踊り・ダンスによって相手に効果や死亡条件を与えますか？",
    "prophecy_power": "死の預言など、条件達成で後から死亡・勝利判定になる印を付けますか？",
    "extra_vote_power": "追加票や複数票を持ちますか？",
    "special_vote_power": "会議中に専用の特殊投票を対象に入れる能力ですか？",
    "body_evolve_power": "死体を捕食・処理することで自身の能力やキルクールが強化されますか？",
    "body_color_power": "死体の色や見た目を変える能力ですか？",
    "fake_body_power": "通報できない偽物の死体を作れますか？",
    "fake_player_power": "偽物のプレイヤーやダミーの姿を作れますか？",
    "role_reveal_boost_power": "自分の役職を公開することで移動速度やキル性能が強化されますか？",
    "body_unreportable_power": "死体を通報できない状態にできますか？",
    "special_vent_power": "特殊ベントを設置・強化・再リンクする能力ですか？",
    "task_rollback_power": "他人の完了済みタスクを巻き戻せますか？",
    "global_task_replace_power": "全プレイヤーの完了済みタスクを別タスクに置き換えますか？",
    "trash_cleanup_death_power": "\u30de\u30c3\u30d7\u4e0a\u306b\u843d\u3061\u305f\u30b4\u30df\u3092\u62fe\u308f\u306a\u3044\u3068\u6b7b\u4ea1\u3059\u308b\u5f79\u8077\u3067\u3059\u304b\uff1f",
    "muscle_task_pose_power": "\u30bf\u30b9\u30af\u3092\u7b4b\u30c8\u30ec\u7cfb\u306b\u7f6e\u304d\u63db\u3048\u3001\u5b8c\u4e86\u5f8c\u306b\u30dd\u30fc\u30ba\u306a\u3069\u3067\u898b\u3048\u308b\u3088\u3046\u306b\u306a\u308a\u307e\u3059\u304b\uff1f",
    "impostor_kill_win_power": "インポスターにキルされることが勝利条件に関わりますか？",
    "sidekick_creation_power": "任意の相手をサイドキックにして同陣営へ引き込めますか？",
    "madkiller_creation_power": "対象の役職をマッドキラーに変更して自陣営を増やせますか？",
    "revenant_creation_power": "幽霊に能力を使い、対象をレヴェナントに変更できますか？",
    "vent_disguise_move_power": "ベントの姿になり、そのベント自体を移動できますか？",
    "fairy_chain_kill_power": "妖精などを付け、すれ違いで移った対象を後からまとめてキルできますか？",
    "kunai_projectile_power": "クナイなどの投擲物を向いている方向へ飛ばしてキルできますか？",
    "launch_explosion_power": "対象を発射し、衝突時の爆発で周囲を巻き込んでキルできますか？",
    "impostor_task_win_power": "クルーのようにタスクを完了してインポスター陣営を勝利させますか？",
    "solo_impostor_unlock_power": "インポスターが複数いる間はキルできず、自分だけになるとキル能力を得ますか？",
    "promotion_power": "味方やサブ役職が条件達成・死亡時に上位役職へ昇格しますか？",
    "live_task_win_power": "生存したまま全タスク完了することが単独勝利条件ですか？",
    "missionary_power": "宣教や神の宣告で対象を後から自決させますか？",
    "forced_kill_misfire_power": "相手のキルボタンを暴発させて強制キルを起こしますか？",
    "obsession_power": "片思いの相手や邪魔者を中心に勝利条件・キル可否が変わりますか？",
    "shrine_power": "社などの設置物で自分を保護しますか？",
    "mine_power": "地雷を設置し、近づいたプレイヤーをキルしますか？",
    "swallow_power": "生存者を丸呑みしてキルし、死体も消しますか？",
    "queen_servant_power": "対象をサーヴァント化し、その行動でクイーンが強化されますか？",
    "bet_target_win_power": "賭けた相手が勝つことで自分も勝利しますか？",
    "skip_win_power": "会議が一定回数スキップされることが勝利条件に関わりますか？",
    "paint_area_win_power": "マップ上を塗った面積が勝利条件に関わりますか？",
    "chimera_creation_power": "相手をキメラにし、何度も復活する味方を作りますか？",
    "shadow_object_power": "影などの設置物を消すことで味方のキルクール等を調整しますか？",
    "ironmate_power": "見た目はクルー同然で、キルを一定回数ブロックできますか？",
    "trash_layer_power": "対象を死亡でも生存でもないゴミ箱のような特殊レイヤーへ送りますか？",
    "curse_suicide_power": "自分の命と引き換えに対象を呪殺・道連れにしますか？",
    "subteam_fallback_power": "特定陣営のサブチーム・フォールバック役職ですか？",
    "jackal_subteam_power": "ジャッカル陣営のサブチーム・フォールバック役職ですか？",
    "mad_teruteru_task_exile_win_power": "タスク完了後に追放されると、インポスター勝利になりますか？",
    "guard_counter_vision_power": "警戒中にキルされると防ぎ、キラーの視界を奪えますか？",
    "will_report_power": "通報時に死体からキル者の役職や色の情報を得られますか？",
    "vote_visibility_power": "会議中、全プレイヤーの投票先を見られますか？",
    "revive_next_turn_power": "自身をキルしたクルーが死亡すると、次のターンに復活できますか？",
    "impostor_judged_crewmate_power": "自覚できず、判定ではインポスターとして扱われるクルーですか？",
    "yandere_subteam_power": "ヤンデレ陣営のサブチーム・フォールバック役職ですか？",
    "queen_subteam_power": "クイーン陣営のサブチーム・フォールバック役職ですか？",
    "nonkill_fallback_power": "フォールバック役職で、基本的にキル能力を持ちませんか？",
    "liberal_fund_power": "リベラル陣営の資金や資金増加率に関わりますか？",
    "untargetable_power": "能力の対象にならない、または投票・キルが無効化されますか？",
    "combination_role_power": "複数役職が1組になっているコンビネーション役職ですか？",
    "assassin_merlin_power": "アサシンとマーリンのように、マーリン推測会議が勝利条件に関わりますか？",
    "merlin_info_power": "マーリンのようにインポスター全員を把握できますか？",
    "hero_villain_set_power": "ヒーロー・ヴィラン・ヴィジランテの三すくみセットに関わりますか？",
    "death_stage_power": "死亡者数や死亡率で段階的に覚醒・強化されますか？",
    "crime_scene_power": "通報された死体の犯行現場を調査しますか？",
    "assistant_report_power": "自分が通報した死体の正確な死亡時刻を知り、捜査官の調査を補助しますか？",
    "apprentice_investigator_power": "相方死亡後に見習い捜査官へ変化しますか？",
    "graffiti_power": "ラクガキを置き、使用回数が後の能力に影響しますか？",
    "wisp_light_power": "灯火を設置し、灯火停電や幽霊勝利に関わりますか？",
    "same_group_awareness_power": "同じ組の相方の位置や状態を常に把握できますか？",
    "support_target_power": "サポート対象の役職や陣営を知る補助役職ですか？",
    "role_guess_kill_power": "会議中に役職を当ててキルする能力ですか？",
    "object_move_power": "マップオブジェクトを動かせますか？",
    "speed_panel_power": "加速パネルなど、踏むと移動速度が変わる設置物を作りますか？",
    "skating_power": "氷上のように滑って加速する移動能力ですか？",
    "vote_swap_power": "会議中に2人の投票先や票を入れ替えますか？",
    "balance_vote_power": "会議中に2人を天秤にかけ、どちらか又は両方を追放する能力ですか？",
    "justice_balance_power": "ジャスティスのように会議で対象を絞って強制的に追放へ持ち込む役職ですか？",
    "dying_message_power": "死亡時にメッセージを残す役職ですか？",
    "sleep_bomb_power": "視界を奪う爆弾・おやすみボムを設置しますか？",
    "tofu_fullness_power": "お揚げや満腹度を管理して生存を狙う役職ですか？",
    "chain_shift_power": "対象と役職を交換する役職ですか？",
    "scarlet_love_power": "キープや本命を選ぶ恋愛系の第三陣営ですか？",
    "tyrant_kill_win_power": "指定数キルすると勝利する第三陣営ですか？",
    "vanity_sheriff_power": "シェリフのように陣営問わずキルできる第三陣営ですか？",
    "opportunist_survival_power": "最後まで生存すると追加勝利する役職ですか？",
    "balance_self_vote_mode_power": "会議で自分に投票してから、天秤にかける2人を選ぶ役職ですか？",
    "balance_self_target_option_power": "設定により、自分自身を審判や天秤の対象にできますか？",
    "balance_restrict_other_abilities_power": "天秤会議中、対象者以外への能力使用を制限する設定がありますか？",
    "traitor_cracking_power": "キル後にアドミン・カメラ・バイタルを遠隔で順番に使えますか？",
    "corpse_guard_charge_power": "死体を処理して誰かを守る回数を増やしますか？",
    "ambush_vent_kill_power": "ベント中やベント付近から特殊キルを行いますか？",
    "second_kill_button_power": "通常キルとは別の二つ目のキルボタンを持ちますか？",
    "puppeteer_kill_power": "自分のキルをキャンセルし、対象に別の相手をキルさせますか？",
    "kill_quota_win_power": "一定数キルしないと、自陣営が勝っても自分だけ勝利できませんか？",
    "lights_only_kill_power": "停電中だけキルクールが溜まり、停電中だけキルできますか？",
    "bounty_target_power": "時間で変わる賞金首をキルするとキルクールが短くなりますか？",
    "curse_target_power": "相手を呪い対象に指定し、その対象をキルするとキルクールが短くなりますか？",
    "kidnap_drag_power": "対象を拘束して連れ回し、後からキルできますか？",
    "curse_proxy_kill_power": "呪った相手に近くの別プレイヤーをキルさせますか？",
    "bait_vent_detection_power": "自分がベイト系で、ベント使用を検知・通知する追加能力がありますか？",
    "stock_reload_power": "会議などで溜まるストックを使ってキルクールを減らしますか？",
    "meeting_kill_power": "会議中に相手を直接キルできますか？",
    "last_impostor_boost_power": "インポスターの残り人数が少ない時に覚醒・強化されますか？",
    "team_cooldown_boost_power": "仲間のインポスターのキルクールも回復・短縮できますか？",
    "kill_combo_power": "キルするたびにコンボが溜まり、キルクールなどが強化されますか？",
    "doll_creation_power": "対象をドールやミニオンのような役職に変化させますか？",
    "object_disguise_power": "マップ上のオブジェクトに変身できますか？",
    "magic_circle_power": "復活などの条件になる魔法陣を設置しますか？",
    "meeting_time_steal_power": "死体を使って会議時間を減らしたり奪ったりしますか？",
    "mushroom_power": "ファングルのキノコなどマップギミックを設置できますか？",
    "custom_sabotage_win_power": "独自サボタージュを起こし、失敗すると特殊勝利になりますか？",
    "bombing_mode_power": "専用画面や指定地点から爆撃を行いますか？",
    "hijack_vision_power": "他プレイヤーの視界を乗っ取って見る能力ですか？",
    "map_device_fake_power": "アドミン・カメラ・バイタルなどの機器情報を偽装しますか？",
    "time_stop_power": "時間を止めて他プレイヤーの移動を止めますか？",
    "weapon_collect_power": "武器を拾ったり合成したりして複数の攻撃能力を使いますか？",
    "punch_launch_power": "相手を殴って吹き飛ばし、壁衝突などでキルしますか？",
    "vote_cancel_power": "会議で対象の得票を打ち消す能力ですか？",
    "vote_zero_power": "投票数が0票になる役職/属性ですか？",
    "task_meeting_time_power": "タスク完了によって会議時間を延長しますか？",
    "task_public_reveal_power": "タスクを完了すると自分の役職が全員に公開されますか？",
    "killer_freeze_on_death_power": "キルされた時、キルした相手を一定時間動けなくしますか？",
    "oil_douse_win_power": "全生存者にオイルを塗り、ベントに入ることで勝利しますか？",
    "egoist_power": "インポスターを認識しつつ、インポスター全滅後に勝利を狙いますか？",
    "pavlov_owner_dog_power": "オーナーが犬を指名し、犬がキル役として行動する役職ですか？",
    "schrodinger_cat_power": "キルされそうになると防御し、キルしてきた相手の陣営に所属しますか？",
    "role_change_to_madmate_power": "対象のプレイヤーの役職をマッドメイトに変更できますか？",
    "location_stay_win_power": "特定の場所に一定時間滞在することが勝利条件ですか？",
    "three_pigs_team_power": "3人1組で、生存数やタスク達成率が勝利条件に関わりますか？",
    "monster_corpse_creation_power": "死体を怪物として蘇生し、操作やキルをさせられますか？",
    "corpse_nest_power": "死体を運び、ベントに隠したり巣にしたりできますか？",
    "blackout_body_unlock_power": "死体数によって特殊な停電能力が解放されますか？",
    "nekomata_revenge_power": "猫又・道連れ系の能力を持ちますか？",
    "suicide_wish_power": "自分の死亡や自殺が勝利・能力条件に関係しますか？",
    "speed_boost_target_power": "自分や対象の移動速度を変化させる能力ですか？",
    "hawk_eye_power": "ホークアイのように一時的に視界を広げて見渡せますか？",
    "door_manipulation_power": "ドアや通路を操作する能力ですか？",
    "safecracker_power": "金庫・暗号・鍵などの解除が勝利や能力に関係しますか？",
    "matryoshka_power": "マトリョーシカのように中身や段階が変化しますか？",
    "god_power": "神・全知系の特殊情報役職ですか？",
    "evil_seer_power": "イビルシーアのように死体や情報を悪用する役職ですか？",
    "black_hat_hack_power": "ブラックハット系のハッキングや感染能力ですか？",
    "false_accuse_power": "冤罪・濡れ衣を扱う役職ですか？",
    "push_drop_power": "突き落としや押し出しで殺害・移動させますか？",
    "technician_power": "修理・技術系の能力ですか？",
    "stuntman_power": "身代わり・スタント・ガード系の能力ですか？",
    "button_power": "ボタンや会議招集に関係する能力ですか？",
    "lighter_power": "ライターのように視界や明かりを強めますか？",
    "hamburger_task_power": "ハンバーガーや追加タスクが能力に関係しますか？",
    "data_hack_power": "データやハッキングで情報を得る役職ですか？",
    "busker_power": "バスカーのように会議・死体・情報を使う役職ですか？",
    "crab_power": "カニ歩きや横移動など独自の移動能力ですか？",
    "tracker_power": "対象を追跡・トラックする役職ですか？",
    "pumpkin_cat_power": "ネコカボチャのようなカボチャ猫系の役職ですか？",
    "moving_record_power": "位置を記録して、その場所へ戻る・移動する能力ですか？",
    "pteranodon_power": "プテラノドンのように移動・飛行系の能力を持ちますか？",
    "toilet_fan_power": "トイレや特定の通路・ドアに関係する役職ですか？",
    "clergyman_power": "聖職者のように周囲へ制限・加護を与える役職ですか？",
    "vulture_power": "死体を食べる・処理することが勝利条件に関係しますか？",
    "onmyoji_power": "陰陽師のように霊的な調査や相方・変化に関わりますか？",
    "remote_control_power": "リモコンのように対象を遠隔操作しますか？",
    "medium_power": "ミーディアムのように死者や霊界から情報を得ますか？",
}

QUIZ_HINTS = {
    "team_crewmate": "クルー陣営の役職です。",
    "team_impostor": "インポスター陣営の役職です。",
    "team_neutral": "第三陣営の役職です。",
    "team_liberal": "リベラル陣営の役職です。リーダーを中心に、資金を貯めて勝利を目指します。",
    "team_madmate": "マッドメイト陣営・狂人系チームです。",
    "team_jackal": "ジャッカル陣営です。",
    "modifier_role": "元の役職に追加される役職・属性です。",
    "nos_role": "NoS / Nebula on the Ship側にもある役職/仕様です。",
    "snr_role": "SuperNewRoles側にもある役職/仕様です。",
    "tohk_role": "TownOfHost-K側にもある役職/仕様です。",
    "exr_role": "Extreme Roles側にもある役職/仕様です。",
    "nos_modifier_role": "NoSのモディファイア役職です。",
    "evil_support_power": "別陣営を助ける補助・狂人系役職です。",
    "host_observer_power": "ホスト専用の観戦・GM系役職です。",
    "host_only_power": "ホストに割り当てられます。",
    "non_counting_power": "生存者数や役職数にカウントされません。",
    "plain_role_power": "特殊能力がほぼない基本役職です。",
    "emergency_repair_power": "緊急タスクやサボを即修理できます。",
    "no_task_role": "タスクを持ちません。",
    "utility_restriction_power": "機器や緊急会議の使用が制限されます。",
    "limited_kill_power": "キル可能回数に上限があります。",
    "task_kill_charge_power": "タスク進捗でキル回数やCTが変わります。",
    "can_kill": "キル能力に関わります。",
    "normal_kill": "通常キルに関わります。",
    "sheriff_misfire_power": "キル不可対象を撃つと誤爆して自分が死亡します。",
    "guess_misfire_power": "役職推測を外すと自分が死亡します。",
    "suicide_button_power": "自分から自決できる能力があります。",
    "serial_suicide_timer_power": "キル後、次のキルを急がないと自殺します。",
    "gamble_cooldown_power": "キル後の抽選結果で次のキルクールが変わります。",
    "target_mismatch_suicide_power": "能力対象を間違えると自分が死亡します。",
    "special_kill": "特殊キルに関わります。",
    "trap_place_power": "マップ上に罠を設置できます。",
    "kill_trap_power": "罠で拘束やキルを狙えます。",
    "notify_trap_power": "罠を踏んだ相手を通知できます。",
    "vent_trap_power": "\u30d9\u30f3\u30c8\u306b\u7f60\u3092\u4ed5\u639b\u3051\u3066\u3001\u4f7f\u7528\u3057\u305f\u30d7\u30ec\u30a4\u30e4\u30fc\u3092\u62d8\u675f\u3067\u304d\u307e\u3059\u304b\uff1f",
    "target_power": "特定の対象を選ぶ能力があります。",
    "target_kill_power": "指定対象のキルが能力や勝利条件に関わります。",
    "guard_piercing_power": "ガードや防御を貫通する能力に関わります。",
    "wave_cannon_power": "波動砲やビームに関わります。",
    "area_instant_kill_power": "近くにいる複数人を一度にキルできます。",
    "projectile_barrage_power": "扇状の弾幕や弾を発射します。",
    "multi_hit_kill_power": "必要ヒット数に達するとキルします。",
    "friendly_fire_option_power": "設定により味方にも当たります。",
    "uses_vent": "ベントを使えます。",
    "can_win_alone": "単独勝利できます。",
    "additional_win": "追加勝利に関わります。",
    "can_protect": "誰かを守る能力があります。",
    "can_investigate": "情報を調べる能力があります。",
    "compare_power": "複数人の関係や陣営を比較します。",
    "meeting_ability": "会議中に強い能力を発揮します。",
    "meeting_message": "会議中や会議後に専用メッセージが出ます。",
    "has_tasks": "タスクがあります。",
    "task_based_power": "タスク進行が能力や勝利条件に関わります。",
    "extra_task_power": "追加タスクや専用タスクに関わります。",
    "death_trigger": "死亡時に能力が発動します。",
    "scheduled_death": "特定タイミングで自動死亡します。",
    "ghost_role": "死亡後や幽霊状態で使う役職です。",
    "nos_ghost_role": "NoSの幽霊役職です。",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わります。",
    "soul_vision_power": "死亡位置に残る霊魂や幽霊を見ることができます。",
    "ghost_crewmate_power": "ゴーストクルー役職です。",
    "ghost_impostor_power": "ゴーストインポスター役職です。",
    "ghost_neutral_power": "ゴーストニュートラル役職です。",
    "ghost_body_move_power": "幽霊状態で死体を動かします。",
    "ghost_sabotage_repair_power": "幽霊状態でサボタージュ修理に干渉します。",
    "ghost_photo_power": "幽霊状態で写真を撮ります。",
    "vent_open_power": "ベント開閉に関わります。",
    "sabotage_cooldown_reset_power": "サボタージュクールを回復します。",
    "ghost_lights_power": "幽霊状態で特殊停電を起こします。",
    "ghost_dummy_power": "幽霊状態でダミーを表示します。",
    "leak_position_power": "位置情報をリークします。",
    "ghost_obstacle_power": "幽霊や障害物で移動を妨害します。",
    "controllable_illusion_power": "操作できる幻像を出します。",
    "ghost_stare_win_power": "生存者のそばで佇むことが勝利条件です。",
    "ghost_light_power": "幽霊状態で光をともします。",
    "corpse_pull_power": "死体を引き寄せます。",
    "ghost_alert_power": "幽霊状態でアラートを鳴らします。",
    "corpse_duplicate_power": "死体を複製して設置します。",
    "ghost_possession_vision_power": "憑依した生存者の視界を変えます。",
    "guardian_angel_judgement_power": "守護天使判定や守護能力ベースの幽霊役職です。",
    "ghost_meeting_button_power": "幽霊状態で緊急会議を起こします。",
    "ghost_noise_mark_power": "対象死亡時にアラートを発動させます。",
    "ghost_cooldown_reset_power": "対象のクールタイムをリセットします。",
    "ghost_role_reveal_power": "対象の役職を会議で公開します。",
    "demon_tracking_power": "対象位置をインポスターへ通知します。",
    "demon_device_disable_power": "生存者の情報機器を妨害します。",
    "demon_vent_open_power": "対象近くのベントを開けます。",
    "demon_sabotage_power": "死亡後にサボタージュを使えます。",
    "assisting_angel_power": "選んだ相手の勝利に乗る支援幽霊役職です。",
    "portable_security_power": "どこでもセキュリティ系情報を見られます。",
    "portable_admin_power": "どこでもアドミン系情報を見られます。",
    "portable_vitals_power": "どこでもバイタルを確認できます。",
    "death_cause_power": "死亡したプレイヤーの死因が分かります。",
    "task_delegation_power": "タスクの肩代わりや委任に関わります。",
    "kill_notification_power": "キル発生時の通知や方向情報に関わります。",
    "kill_flash_power": "死亡発生時にキルフラッシュを受けます。",
    "time_rewind_power": "キルや移動を巻き戻します。",
    "guard_sacrifice_power": "誰かを守るために身代わりになります。",
    "counter_power": "攻撃を防いだり反撃したりします。",
    "body_curse_power": "死体を使ってキラーへ呪いや効果を与えます。",
    "camera_install_power": "カメラや監視装置を設置します。",
    "vent_usage_analysis_power": "\u30d9\u30f3\u30c8\u3092\u5206\u6790\u3057\u3066\u3001\u524d\u30bf\u30fc\u30f3\u306e\u4f7f\u7528\u60c5\u5831\u3092\u5f97\u3089\u308c\u307e\u3059\u304b\uff1f",
    "lantern_place_light_power": "\u30e9\u30f3\u30bf\u30f3\u3084\u706f\u308a\u3092\u8a2d\u7f6e\u3057\u3066\u3001\u5468\u56f2\u3092\u7167\u3089\u3059\u3053\u3068\u304c\u3067\u304d\u307e\u3059\u304b\uff1f",
    "drone_control_power": "\u30c9\u30ed\u30fc\u30f3\u3092\u547c\u3073\u51fa\u3057\u3066\u8996\u70b9\u3092\u64cd\u4f5c\u3067\u304d\u307e\u3059\u304b\uff1f",
    "drone_task_reveal_power": "\u30c9\u30ed\u30fc\u30f3\u306e\u8fd1\u304f\u3092\u901a\u3063\u305f\u30d7\u30ec\u30a4\u30e4\u30fc\u306e\u30bf\u30b9\u30af\u60c5\u5831\u3092\u78ba\u8a8d\u3067\u304d\u307e\u3059\u304b\uff1f",
    "vent_block_power": "ベントを封鎖したり使用不能にします。",
    "survival_requirement_power": "生存や特定条件達成が勝利に関わります。",
    "photo_power": "写真や記録として位置情報を残します。",
    "random_teleport_power": "ランダムな位置へテレポートさせます。",
    "mass_teleport_power": "生存者全員を集合テレポートさせます。",
    "teleport_kill_swap_power": "対象と位置を入れ替えながらキルします。",
    "self_resurrection_power": "死亡後に復活できます。",
    "variable_vote_power": "投票数がランダムまたは設定値で変化します。",
    "portal_power": "ポータルや2点間移動に関わります。",
    "meeting_time_power": "会議時間を延長・短縮・変更します。",
    "noncrew_count_power": "クルー以外の人数や役職数を把握できます。",
    "forced_report_power": "強制通報を発生させます。",
    "jail_power": "対象を拘束・投獄します。",
    "summon_power": "対象や死体を呼び寄せます。",
    "exorcism_power": "死体や対象に祈り・除霊系の効果を与えます。",
    "stress_power": "近くにいることや時間経過で危険度が増します。",
    "exile_resurrection_power": "追放後に復活します。",
    "echo_scan_power": "範囲内のプレイヤーや死体を検知します。",
    "action_detection_power": "能力使用や行動を検知します。",
    "vote_power": "投票や会議結果に干渉します。",
    "exile_win": "追放されることが勝利条件に関わります。",
    "tracking_power": "位置や移動を追跡できます。",
    "role_info_power": "役職や陣営情報を知る能力があります。",
    "omniscient_power": "全員の役職を常に見ることができます。",
    "public_identity": "存在や役職が他人に分かります。",
    "star_visual_power": "スター系の見た目や発光で目立ちます。",
    "fake_identity": "別陣営や別役職のように見える要素があります。",
    "dummy_power": "ダミーや分身を表示します。",
    "body_info_power": "死体・死因・死亡位置に関わります。",
    "corpse_psychometry_power": "\u6b7b\u4f53\u3092\u8aad\u307f\u53d6\u3063\u3066\u3001\u6b7b\u56e0\u30fb\u6b7b\u4ea1\u6642\u523b\u30fb\u72af\u4eba\u306e\u8db3\u8de1\u306a\u3069\u3092\u8abf\u3079\u3089\u308c\u307e\u3059\u304b\uff1f",
    "body_clear_power": "死体を消したり処理したりできます。",
    "body_move_power": "死体を運んだり動かしたりできます。",
    "corpse_consumption_power": "死体の捕食や消去が勝利・能力に関わります。",
    "delayed_kill": "遅延キルや間接キルに関わります。",
    "vampire_bite_power": "吸血で対象を遅れて死亡させます。",
    "blood_stain_power": "次ターンに血痕が残ります。",
    "thrall_creation_power": "設定により対象を眷属へ変更できます。",
    "collision_kill_power": "接触やすれ違いでキルします。",
    "bomb_power": "爆弾の付与・設置・爆発に関わります。",
    "marker_power": "マーカーや地点指定による範囲能力に関わります。",
    "disguise_or_invisible": "変身・透明化・姿の偽装に関わります。",
    "invisibility_power": "自分自身が透明化できます。",
    "shapeshift_power": "他プレイヤーの姿に変身できます。",
    "global_camouflage_power": "全員の見た目をまとめて隠します。",
    "growth_size_power": "時間経過で見た目が大きくなります。",
    "area_effect": "周囲や部屋全体に影響します。",
    "sabotage_power": "サボタージュに関わります。",
    "lights_sabotage_power": "停電サボタージュに特化しています。",
    "critical_sabotage_power": "リアクター・O2などに特化しています。",
    "door_power": "ドアに干渉します。",
    "specific_door_power": "特定の場所や設備のドアに干渉します。",
    "revenge_kill": "道連れや復讐キルに関わります。",
    "suicide_risk": "能力や条件で自滅する可能性があります。",
    "conversion_power": "他人の状態や役職を変えます。",
    "appoint_power": "対象を特定の役職に任命・転職させます。",
    "infection_power": "感染や拡散に関わります。",
    "partner_power": "特定の相手との関係に関わります。",
    "lovers_power": "ラバーズや恋人関係に関わります。",
    "lovers_attribute_power": "他の役職に重複するラバーズ属性です。",
    "alignment_shift_power": "陣営や勝利条件が途中で変わります。",
    "control_power": "他人を操作できます。",
    "restriction_power": "他人の行動や移動を制限します。",
    "ranged_power": "遠距離から能力やキルを使えます。",
    "wall_piercing_power": "壁や障害物越しに能力が通ります。",
    "teleport_power": "テレポートや位置移動に関わります。",
    "cooldown_power": "クールダウンを変化させます。",
    "speed_power": "移動速度を変化させます。",
    "movement_power": "移動方法や足場に干渉します。",
    "stationary_death_power": "止まっていると死亡する制約があります。",
    "environmental_death_power": "ドア・ベント・はしご等の環境で死亡する可能性があります。",
    "report_power": "通報や緊急会議ボタンに干渉します。",
    "vision_power": "視界に干渉します。",
    "swap_power": "投票先・位置・役職などを入れ替えます。",
    "fate_swap_power": "会議中に選んだ2人の役職や票を入れ替えます。",
    "dance_power": "踊り・ダンスで能力を発動します。",
    "prophecy_power": "死の預言や印による後発効果に関わります。",
    "extra_vote_power": "追加票や複数票に関わります。",
    "special_vote_power": "会議中の専用特殊投票に関わります。",
    "body_evolve_power": "死体を捕食・処理して自身を強化します。",
    "body_color_power": "死体の色や見た目を変えられます。",
    "fake_body_power": "偽物の死体を作れます。",
    "fake_player_power": "偽物のプレイヤーやダミーを作れます。",
    "role_reveal_boost_power": "役職公開による自己強化に関わります。",
    "body_unreportable_power": "死体を通報できない状態にできます。",
    "special_vent_power": "特殊ベントやベントリンクに関わります。",
    "task_rollback_power": "他人のタスクを巻き戻せます。",
    "global_task_replace_power": "全員の完了済みタスクを置き換えます。",
    "trash_cleanup_death_power": "\u30de\u30c3\u30d7\u4e0a\u306b\u843d\u3061\u305f\u30b4\u30df\u3092\u62fe\u308f\u306a\u3044\u3068\u6b7b\u4ea1\u3059\u308b\u5f79\u8077\u3067\u3059\u304b\uff1f",
    "muscle_task_pose_power": "\u30bf\u30b9\u30af\u3092\u7b4b\u30c8\u30ec\u7cfb\u306b\u7f6e\u304d\u63db\u3048\u3001\u5b8c\u4e86\u5f8c\u306b\u30dd\u30fc\u30ba\u306a\u3069\u3067\u898b\u3048\u308b\u3088\u3046\u306b\u306a\u308a\u307e\u3059\u304b\uff1f",
    "impostor_kill_win_power": "インポスターにキルされることが勝利に関わります。",
    "sidekick_creation_power": "相手をサイドキック化できます。",
    "madkiller_creation_power": "対象をマッドキラーに変更します。",
    "revenant_creation_power": "幽霊を使って対象をレヴェナントに変更します。",
    "vent_disguise_move_power": "ベントの姿になり、そのベントを移動できます。",
    "fairy_chain_kill_power": "妖精などがすれ違いで移り、後からキルします。",
    "kunai_projectile_power": "クナイなどを投げてヒット数でキルします。",
    "launch_explosion_power": "対象を発射し、衝突爆発で周囲を巻き込みます。",
    "impostor_task_win_power": "タスク完了でインポスター陣営を勝利させます。",
    "solo_impostor_unlock_power": "自分だけのインポスターになるとキル能力を得ます。",
    "promotion_power": "味方やサブ役職が上位役職へ昇格します。",
    "live_task_win_power": "生存中の全タスク完了が勝利条件です。",
    "missionary_power": "宣教や神の宣告で対象を自決させます。",
    "forced_kill_misfire_power": "相手のキルボタンを暴発させます。",
    "obsession_power": "片思いや邪魔者が勝利条件に関わります。",
    "shrine_power": "社などの設置物で保護を得ます。",
    "mine_power": "地雷を設置します。",
    "swallow_power": "丸呑みで生存者をキルし死体を消します。",
    "queen_servant_power": "サーヴァント化とクイーン強化に関わります。",
    "bet_target_win_power": "賭けた相手の勝利に乗ります。",
    "skip_win_power": "会議スキップ回数が勝利条件に関わります。",
    "paint_area_win_power": "塗った面積が勝利条件に関わります。",
    "chimera_creation_power": "復活するキメラを作ります。",
    "shadow_object_power": "影などの設置物に関わります。",
    "ironmate_power": "クルー同然の見た目とキルブロックに関わります。",
    "trash_layer_power": "対象を特殊なゴミ箱レイヤーへ送ります。",
    "curse_suicide_power": "自分の命と引き換えに呪殺します。",
    "subteam_fallback_power": "サブチーム・フォールバック役職です。",
    "jackal_subteam_power": "ジャッカル陣営のサブチームに関わります。",
    "mad_teruteru_task_exile_win_power": "タスク完了後の追放でインポスター勝利を狙います。",
    "guard_counter_vision_power": "警戒中のキルを防ぎ、キラーの視界を奪います。",
    "will_report_power": "通報時に死体からキル者情報を読み取ります。",
    "vote_visibility_power": "全プレイヤーの投票先が見えます。",
    "revive_next_turn_power": "自分をキルしたクルーの死亡で次ターンに復活できます。",
    "impostor_judged_crewmate_power": "クルーなのにインポスター判定されます。",
    "yandere_subteam_power": "ヤンデレ陣営のサブチームに関わります。",
    "queen_subteam_power": "クイーン陣営のサブチームに関わります。",
    "nonkill_fallback_power": "基本的にキルを持たないフォールバック役職です。",
    "liberal_fund_power": "リベラル陣営の資金に関わります。",
    "untargetable_power": "対象不可や投票・キル無効に関わります。",
    "combination_role_power": "複数役職が1組のセットです。",
    "assassin_merlin_power": "アサシンとマーリンの特殊会議に関わります。",
    "merlin_info_power": "インポスター全員を把握できます。",
    "hero_villain_set_power": "ヒーロー・ヴィラン・ヴィジランテのセットに関わります。",
    "death_stage_power": "死亡者数や死亡率で段階強化されます。",
    "crime_scene_power": "犯行現場の調査に関わります。",
    "assistant_report_power": "通報死体の死亡時刻や捜査官補助に関わります。",
    "apprentice_investigator_power": "見習い捜査官への変化に関わります。",
    "graffiti_power": "ラクガキに関わります。",
    "wisp_light_power": "灯火や灯火停電に関わります。",
    "same_group_awareness_power": "同じ組の相方情報を把握できます。",
    "support_target_power": "サポート対象の役職を知ります。",
    "role_guess_kill_power": "役職当てキルに関わります。",
    "object_move_power": "マップオブジェクトを動かします。",
    "speed_panel_power": "加速パネルを設置します。",
    "skating_power": "滑る移動能力に関わります。",
    "vote_swap_power": "会議中の票入れ替えに関わります。",
    "balance_vote_power": "天秤投票で対象2人の追放に関わります。",
    "justice_balance_power": "ジャスティス系の審判会議で追放先を絞ります。",
    "dying_message_power": "死亡時にメッセージを残します。",
    "sleep_bomb_power": "視界を奪うおやすみボムを設置します。",
    "tofu_fullness_power": "お揚げや満腹度を管理して生存を狙います。",
    "chain_shift_power": "対象と役職を交換します。",
    "scarlet_love_power": "キープや本命を選ぶ恋愛系第三陣営です。",
    "tyrant_kill_win_power": "指定数キルすることで勝利します。",
    "vanity_sheriff_power": "シェリフのように陣営問わずキルできます。",
    "opportunist_survival_power": "最後まで生存すると追加勝利します。",
    "balance_self_vote_mode_power": "自投票で天秤モードに入り、2人を選びます。",
    "balance_self_target_option_power": "自分自身を審判や天秤の対象にできる設定があります。",
    "balance_restrict_other_abilities_power": "天秤会議中の能力使用制限設定があります。",
    "traitor_cracking_power": "キル後のクラッキングに関わります。",
    "corpse_guard_charge_power": "死体処理で防御回数を増やします。",
    "ambush_vent_kill_power": "ベントを使った奇襲キルに関わります。",
    "second_kill_button_power": "二つ目のキルボタンを持ちます。",
    "puppeteer_kill_power": "対象に別の相手をキルさせます。",
    "kill_quota_win_power": "一定数キルしないと勝利に乗れません。",
    "lights_only_kill_power": "停電中だけキル可能です。",
    "bounty_target_power": "賞金首キルでキルクールが短くなります。",
    "curse_target_power": "呪い対象キルでキルクールが短くなります。",
    "kidnap_drag_power": "対象を拘束して連れ回します。",
    "curse_proxy_kill_power": "呪った相手に近くの人をキルさせます。",
    "bait_vent_detection_power": "ベイト系でベント使用も検知できます。",
    "stock_reload_power": "ストックやリロードでキルクールを減らします。",
    "meeting_kill_power": "会議中にキルできます。",
    "last_impostor_boost_power": "インポスター残数による覚醒・強化に関わります。",
    "team_cooldown_boost_power": "仲間のキルクールも短縮できます。",
    "kill_combo_power": "キルコンボで自身を強化します。",
    "doll_creation_power": "対象をドールやミニオンに変化させます。",
    "object_disguise_power": "マップオブジェクトに変身できます。",
    "magic_circle_power": "魔法陣の設置に関わります。",
    "meeting_time_steal_power": "死体を使って会議時間を減らします。",
    "mushroom_power": "キノコなどのマップギミックを設置します。",
    "custom_sabotage_win_power": "独自サボタージュによる特殊勝利に関わります。",
    "bombing_mode_power": "指定地点への爆撃に関わります。",
    "hijack_vision_power": "他人の視界を乗っ取って見ます。",
    "map_device_fake_power": "マップ機器の情報を偽装します。",
    "time_stop_power": "時間停止に関わります。",
    "weapon_collect_power": "武器の取得・合成に関わります。",
    "punch_launch_power": "相手を吹き飛ばしてキルします。",
    "vote_cancel_power": "対象の得票を打ち消します。",
    "buff_modifier_power": "バフ属性です。",
    "debuff_modifier_power": "デバフ属性です。",
    "sabotage_repair_restriction_power": "特定のサボタージュ修理が制限されます。",
    "kill_range_modifier_power": "キル距離を変更します。",
    "kill_power_boost_power": "通常キルの威力を上げます。",
    "extra_win_condition_power": "追加の勝利条件や勝利阻害条件があります。",
    "task_progress_display_power": "タスク進捗を表示できます。",
    "blood_trail_power": "キラーに痕跡を残します。",
    "cursor_reveal_power": "会議中の操作情報が見えます。",
    "appearance_shuffle_power": "見た目をシャッフルします。",
    "room_door_open_power": "部屋のドアをまとめて開けます。",
    "trilemma_power": "3人組の勝利条件に関わります。",
    "vision_debuff_power": "視界が狭くなるデバフです。",
    "vote_zero_power": "投票数が0票になります。",
    "task_meeting_time_power": "タスク完了で会議時間が延びます。",
    "task_public_reveal_power": "タスク完了で自分の役職が全員に公開されます。",
    "killer_freeze_on_death_power": "キルした相手を拘束します。",
    "oil_douse_win_power": "全員にオイルを塗ってベントに入る勝利条件です。",
    "egoist_power": "インポスターを認識するが、インポスターとは競合します。",
    "pavlov_owner_dog_power": "オーナーが犬を作り、犬はキル能力を持ちます。",
    "schrodinger_cat_power": "特定のキルを防いで、その相手の陣営に変化します。",
    "role_change_to_madmate_power": "対象の役職をマッドメイトに変更します。",
    "location_stay_win_power": "特定の場所に滞在することが勝利条件です。",
    "three_pigs_team_power": "3人1組の非キル第三陣営です。",
    "monster_corpse_creation_power": "死体を怪物として蘇生し操作します。",
    "corpse_nest_power": "死体を巣にしたベントへ運べます。",
    "blackout_body_unlock_power": "死体数で特殊停電が解放されます。",}


@dataclass(frozen=True)
class Role:
    name: str
    display_name: str
    mod: str
    features: dict[str, bool | None]


def parse_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "yes", "y", "1", "はい"}:
        return True
    if normalized in {"false", "no", "n", "0", "いいえ"}:
        return False
    return None


def normalize_mod_name(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "Unknown"
    key = raw.lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    compact_key = key.replace(" ", "")
    return MOD_ALIASES.get(key) or MOD_ALIASES.get(compact_key) or raw


def load_intro_quiz_metadata() -> dict:
    if not INTRO_QUIZ_DATA_PATH.exists():
        return {"mods": {}, "roles": {}}
    with INTRO_QUIZ_DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_intro_quiz_wiki_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    normalized = url.strip()
    if not normalized:
        return None
    placeholder_values = {"未登録", "none", "null", "n/a", "-", "(未登録)"}
    if normalized.lower() in {value.lower() for value in placeholder_values}:
        return None
    return normalized


def _normalize_intro_quiz_entry(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    cleaned = dict(entry)
    wiki_url = _normalize_intro_quiz_wiki_url(cleaned.get("wiki_url"))
    cleaned["wiki_url"] = wiki_url
    if not cleaned.get("intro_text"):
        cleaned["intro_text"] = None
    return cleaned


def _intro_quiz_role_candidates(role: Role) -> list[str]:
    candidates: list[str] = []
    if role.mod and role.name:
        candidates.append(f"{role.mod}_{role.name}")
    if role.name:
        candidates.append(role.name)
    if role.display_name:
        candidates.append(role.display_name)
    if role.mod and role.display_name:
        candidates.append(f"{role.mod}_{role.display_name}")
    if role.name and "_" in role.name:
        _, suffix = role.name.split("_", 1)
        if suffix:
            candidates.append(suffix)
            if role.mod:
                candidates.append(f"{role.mod}_{suffix}")
    # preserve insertion order while removing duplicates
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def find_intro_quiz_metadata(role: Role, metadata: dict | None = None) -> dict | None:
    data = metadata or load_intro_quiz_metadata()
    roles_data = data.get("roles", {})
    for candidate in _intro_quiz_role_candidates(role):
        if candidate in roles_data:
            return _normalize_intro_quiz_entry(roles_data[candidate])
    return None


def has_intro_quiz_support(role: Role, metadata: dict | None = None) -> bool:
    data = metadata or load_intro_quiz_metadata()
    if find_intro_quiz_metadata(role, data):
        return True
    mod_meta = data.get("mods", {}).get(role.mod)
    return bool(mod_meta and (mod_meta.get("wiki_url") or mod_meta.get("label")))


def filter_roles_for_intro_quiz(roles: list[Role], mod: str | None = None) -> list[Role]:
    selected_mod = normalize_mod_name(mod) if mod else None
    filtered = []
    for role in roles:
        if not selected_mod:
            continue
        if normalize_mod_name(role.mod).lower() != selected_mod.lower():
            continue
        if normalize_mod_name(role.mod) == "Vanilla":
            continue
        filtered.append(role)
    return filtered


TEAM_QUESTION_KEYS = {
    "team_crewmate",
    "team_impostor",
    "team_neutral",
    "team_liberal",
    "team_madmate",
    "team_jackal",
}


def load_roles() -> list[Role]:
    if not DATA_PATH.exists():
        return []

    roles: list[Role] = []
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            if parse_bool(row.get("hidden")) is True:
                continue
            display_name = (row.get("display_name") or name).strip()
            team = (row.get("team") or "").strip().lower()
            features = {
                key: parse_bool(row.get(key))
                for key in FEATURE_QUESTIONS
                if not key.startswith("team_")
            }
            features["team_crewmate"] = team == "crewmate"
            features["team_impostor"] = team == "impostor"
            features["team_neutral"] = team == "neutral"
            features["team_liberal"] = team == "liberal"
            features["team_madmate"] = team == "madmate"
            features["team_jackal"] = team == "jackal"
            for team_key in TEAM_QUESTION_KEYS:
                explicit_team_value = parse_bool(row.get(team_key))
                if explicit_team_value is not None:
                    features[team_key] = explicit_team_value
            mod = normalize_mod_name(row.get("mod"))
            roles.append(
                Role(
                    name=name,
                    display_name=display_name,
                    mod=mod,
                    features=features,
                )
            )
    return roles


QUESTION_PRIORITY_BONUS = {
    "team_crewmate": 1.8,
    "team_impostor": 1.8,
    "team_neutral": 1.8,
    "team_liberal": 1.8,
    "team_madmate": 1.8,
    "team_jackal": 1.8,
    "ghost_role": 1.7,
    "modifier_role": 1.6,
    "nos_role": 1.45,
    "snr_role": 1.45,
    "tohk_role": 1.45,
    "exr_role": 1.45,
    "nos_modifier_role": 1.55,
    "nos_ghost_role": 1.55,
    "host_observer_power": 1.6,
    "can_kill": 1.5,
    "sheriff_misfire_power": 1.9,
    "guess_misfire_power": 1.9,
    "suicide_button_power": 1.65,
    "serial_suicide_timer_power": 2.0,
    "gamble_cooldown_power": 2.0,
    "target_mismatch_suicide_power": 1.75,
    "vampire_bite_power": 2.1,
    "blood_stain_power": 1.95,
    "thrall_creation_power": 1.9,
    "area_instant_kill_power": 2.1,
    "wave_cannon_power": 2.15,
    "projectile_barrage_power": 2.15,
    "multi_hit_kill_power": 2.05,
    "friendly_fire_option_power": 1.85,
    "can_win_alone": 1.5,
    "additional_win": 1.75,
    "exile_win": 1.95,
    "survival_requirement_power": 1.75,
    "meeting_ability": 1.2,
    "vote_power": 1.2,
    "special_vote_power": 1.35,
    "balance_vote_power": 2.2,
    "justice_balance_power": 1.85,
    "dying_message_power": 1.75,
    "sleep_bomb_power": 1.8,
    "tofu_fullness_power": 1.9,
    "chain_shift_power": 1.85,
    "scarlet_love_power": 1.85,
    "tyrant_kill_win_power": 1.9,
    "vanity_sheriff_power": 1.9,
    "opportunist_survival_power": 1.75,
    "balance_self_vote_mode_power": 1.95,
    "balance_self_target_option_power": 1.95,
    "balance_restrict_other_abilities_power": 1.95,
    "sidekick_creation_power": 1.7,
    "madkiller_creation_power": 2.1,
    "revenant_creation_power": 2.1,
    "vent_disguise_move_power": 2.0,
    "fairy_chain_kill_power": 2.05,
    "kunai_projectile_power": 2.1,
    "launch_explosion_power": 2.1,
    "impostor_task_win_power": 2.1,
    "solo_impostor_unlock_power": 2.0,
    "pavlov_owner_dog_power": 2.2,
    "oil_douse_win_power": 2.0,
    "egoist_power": 2.0,
    "invisibility_power": 1.8,
    "disguise_or_invisible": 1.9,
    "shapeshift_power": 1.8,
    "lights_only_kill_power": 2.1,
    "bounty_target_power": 2.0,
    "curse_target_power": 2.0,
    "kidnap_drag_power": 2.0,
    "curse_proxy_kill_power": 2.0,
    "mass_teleport_power": 2.0,
    "teleport_kill_swap_power": 2.0,
    "teleport_power": 1.85,
    "global_camouflage_power": 2.0,
    "star_visual_power": 1.9,
    "growth_size_power": 2.0,
    "collision_kill_power": 2.0,
    "task_public_reveal_power": 1.9,
    "trap_place_power": 1.9,
    "kill_trap_power": 1.9,
    "notify_trap_power": 1.9,
    "vent_trap_power": 2.05,
    "portable_vitals_power": 1.6,
    "death_cause_power": 1.7,
    "kill_flash_power": 1.7,
    "soul_vision_power": 1.7,
    "tracking_power": 1.7,
    "buff_modifier_power": 1.7,
    "debuff_modifier_power": 1.7,
    "environmental_death_power": 1.95,
    "stationary_death_power": 1.85,
    "meeting_message": 1.75,
    "emergency_repair_power": 1.85,
    "stock_reload_power": 1.85,
    "bait_vent_detection_power": 1.8,
    "forced_kill_misfire_power": 1.8,
    "lovers_power": 1.6,
    "queen_servant_power": 1.7,
    "chimera_creation_power": 1.7,
    "trash_layer_power": 1.7,
    "weapon_collect_power": 1.6,
    "ghost_crewmate_power": 1.5,
    "ghost_impostor_power": 1.5,
    "ghost_neutral_power": 1.5,

    "corpse_psychometry_power": 2.05,
    "vent_usage_analysis_power": 2.0,
    "lantern_place_light_power": 2.0,
    "drone_control_power": 2.05,
    "drone_task_reveal_power": 2.0,
    "trash_cleanup_death_power": 2.05,
    "muscle_task_pose_power": 2.0,
    "mad_teruteru_task_exile_win_power": 2.1,
    "guard_counter_vision_power": 2.1,
    "will_report_power": 2.05,
    "vote_visibility_power": 2.0,
    "revive_next_turn_power": 2.05,
    "impostor_judged_crewmate_power": 2.0,
    "role_change_to_madmate_power": 2.05,
    "location_stay_win_power": 2.1,
    "three_pigs_team_power": 2.15,
    "monster_corpse_creation_power": 2.15,
    "corpse_nest_power": 2.05,
    "blackout_body_unlock_power": 2.05,
    "nekomata_revenge_power": 2.35,
    "suicide_wish_power": 2.2,
    "speed_boost_target_power": 2.15,
    "hawk_eye_power": 2.2,
    "door_manipulation_power": 2.15,
    "safecracker_power": 2.25,
    "matryoshka_power": 2.25,
    "god_power": 2.25,
    "evil_seer_power": 2.2,
    "black_hat_hack_power": 2.2,
    "false_accuse_power": 2.2,
    "push_drop_power": 2.2,
    "technician_power": 2.15,
    "stuntman_power": 2.15,
    "button_power": 2.1,
    "lighter_power": 2.1,
    "hamburger_task_power": 2.15,
    "data_hack_power": 2.15,
    "busker_power": 2.15,
    "crab_power": 2.2,
    "tracker_power": 2.1,
    "pumpkin_cat_power": 2.35,
    "moving_record_power": 2.3,
    "pteranodon_power": 2.3,
    "toilet_fan_power": 2.25,
    "clergyman_power": 2.25,
    "vulture_power": 2.25,
    "onmyoji_power": 2.25,
    "remote_control_power": 2.25,
    "medium_power": 2.2,
}

TEAM_YES_FEATURE_SKIP = {
    "team_crewmate": {
        "bounty_target_power",
        "curse_target_power",
        "kidnap_drag_power",
        "curse_proxy_kill_power",
        "serial_suicide_timer_power",
        "gamble_cooldown_power",
        "lights_only_kill_power",
        "puppeteer_kill_power",
        "kill_quota_win_power",
        "teleport_kill_swap_power",
        "ambush_vent_kill_power",
        "second_kill_button_power",
    },
    "team_impostor": {
        "forced_report_power",
        "bait_vent_detection_power",
        "killer_freeze_on_death_power",
        "portable_vitals_power",
        "death_cause_power",
        "soul_vision_power",
        "task_public_reveal_power",
    },
    "team_neutral": {
        "sheriff_misfire_power",
        "bait_vent_detection_power",
        "killer_freeze_on_death_power",
        "task_public_reveal_power",
    },
}


def team_questions_to_skip(answered_key: str) -> set[str]:
    skipped_features = set(TEAM_YES_FEATURE_SKIP.get(answered_key, set()))
    if answered_key == "team_crewmate":
        # Some support roles are presented like crewmates in play, so leave
        # these two follow-up team checks available after a crewmate "yes".
        return (TEAM_QUESTION_KEYS - {"team_madmate", "team_jackal"}) | skipped_features
    if answered_key == "team_impostor":
        return (TEAM_QUESTION_KEYS - {"team_madmate"}) | skipped_features
    if answered_key == "team_neutral":
        return (TEAM_QUESTION_KEYS - {"team_jackal"}) | skipped_features
    return set(TEAM_QUESTION_KEYS) | skipped_features


def team_answer_matches(role: Role, key: str, answer: bool | None) -> bool:
    feature = role.features.get(key)
    if feature == answer:
        return True
    if answer is not True:
        return False
    if role.features.get("modifier_role") is True:
        return key != "team_liberal"
    if key == "team_impostor" and role.features.get("team_madmate") is True:
        return True
    if key == "team_neutral" and role.features.get("team_jackal") is True:
        return True
    if key == "team_crewmate" and (
        role.features.get("team_madmate") is True
        or role.features.get("team_jackal") is True
    ):
        return True
    return False


def priority_bonus(key: str) -> float:
    explicit_bonus = QUESTION_PRIORITY_BONUS.get(key, 0)
    try:
        order_index = list(FEATURE_QUESTIONS).index(key)
    except ValueError:
        return explicit_bonus
    # Keep CSV/dictionary order meaningful as a gentle tie-breaker, without
    # overpowering the information-gain score or the random top-pool selection.
    order_bonus = max(0, len(FEATURE_QUESTIONS) - order_index) * 0.003
    return explicit_bonus + order_bonus


def answer_match_count(candidates: list[Role], key: str, answer: bool | None) -> int:
    count = 0
    for role in candidates:
        if key in TEAM_QUESTION_KEYS and team_answer_matches(role, key, answer):
            count += 1
            continue
        feature = role.features.get(key)
        if feature == answer:
            count += 1
            continue
        if answer is False and feature is None:
            count += 1
            continue
        if key == "has_tasks" and feature is None:
            count += 1
    return count


def best_question(candidates: list[Role], asked: set[str]) -> str | None:
    scored: list[tuple[float, str]] = []
    candidate_count = len(candidates)
    for key in FEATURE_QUESTIONS:
        if key in asked:
            continue
        yes_count = sum(1 for role in candidates if role.features.get(key) is True)
        no_count = sum(1 for role in candidates if role.features.get(key) is False)
        if yes_count == 0 and no_count == 0:
            continue
        true_match_count = answer_match_count(candidates, key, True)
        false_match_count = answer_match_count(candidates, key, False)
        unknown_match_count = answer_match_count(candidates, key, None)
        if (
            true_match_count == candidate_count
            or false_match_count == candidate_count
            or unknown_match_count == candidate_count
        ):
            continue
        # Blank feature cells are treated flexibly on answer application: a "no"
        # keeps unknown roles, while a "yes" keeps only explicit positives.
        # Score questions by that effective split so rare but distinctive
        # positive tags, such as balance_vote_power, are not buried forever.
        effective_known_count = max(true_match_count, false_match_count, unknown_match_count)
        balance = min(
            match_count
            for match_count in (true_match_count, false_match_count, unknown_match_count)
            if match_count > 0
        )
        coverage_bonus = effective_known_count * 0.05
        one_sided_bonus = 0.25 if yes_count == 0 or no_count == 0 else 0
        # Once the list is small, prefer a real differentiator over a long run
        # of high-priority one-sided "no" questions.
        split_bonus = 4.0 if len(candidates) <= 5 and 0 < true_match_count < candidate_count else 0
        score = balance + coverage_bonus + one_sided_bonus + split_bonus + priority_bonus(key)
        scored.append((score, key))
    if not scored:
        return None

    scored.sort(reverse=True)
    best_score = scored[0][0]
    tolerance = max(0.35, best_score * 0.08)
    top_pool = [(score, key) for score, key in scored if best_score - score <= tolerance]
    top_pool = top_pool[:6]
    weights = [max(0.1, score - (best_score - tolerance) + 0.1) for score, _ in top_pool]
    return random.choices([key for _, key in top_pool], weights=weights, k=1)[0]


class GuessSession:
    def __init__(self, user_id: int, roles: list[Role], selected_mod: str | None = None):
        self.user_id = user_id
        self.all_roles = roles[:]
        self.candidates = roles[:]
        self.selected_mod = selected_mod
        self.asked: set[str] = set()
        self.current_question: str | None = None
        self.last_result_names: set[str] = set()
        self.rejected_names: set[str] = set()
        self.positive_answer_count = 0
        self.answered_question_count = 0
        self.history: list[
            tuple[list[Role], set[str], str | None, set[str], set[str], int, int]
        ] = []

    def can_go_back(self) -> bool:
        return bool(self.history)

    def push_history(self) -> None:
        self.history.append(
            (
                self.candidates[:],
                set(self.asked),
                self.current_question,
                set(self.last_result_names),
                set(self.rejected_names),
                self.positive_answer_count,
                self.answered_question_count,
            )
        )

    def go_back(self) -> bool:
        if not self.history:
            return False
        (
            self.candidates,
            self.asked,
            self.current_question,
            self.last_result_names,
            self.rejected_names,
            self.positive_answer_count,
            self.answered_question_count,
        ) = self.history.pop()
        return True

    def apply_answer(self, answer: bool | None) -> None:
        if not self.current_question:
            return
        key = self.current_question
        self.answered_question_count += 1
        if answer is True:
            self.positive_answer_count += 1
        if key.startswith("guess:"):
            if answer is None:
                return
            guessed_name = key.removeprefix("guess:")
            if answer:
                self.candidates = [role for role in self.candidates if role.name == guessed_name]
            else:
                self.candidates = [role for role in self.candidates if role.name != guessed_name]
            return

        if answer is True and key in TEAM_QUESTION_KEYS:
            self.asked.update(team_questions_to_skip(key))

        matched = []
        for role in self.candidates:
            if key in TEAM_QUESTION_KEYS and team_answer_matches(role, key, answer):
                matched.append(role)
                continue
            feature = role.features.get(key)
            if feature == answer:
                matched.append(role)
                continue
            # Most imported role data is incomplete. A blank feature should not
            # eliminate a role when the user answers "no" to a capability.
            if answer is False and feature is None:
                matched.append(role)
                continue
            # Task assignment can differ between vanilla-like host roles and
            # client/mod roles, so unknown task data should stay flexible.
            if key == "has_tasks" and feature is None:
                matched.append(role)
        if matched:
            self.candidates = matched
            return

        unknown = [
            role
            for role in self.candidates
            if role.features.get(key) is None
        ]
        if unknown:
            self.candidates = unknown

    def next_question(self) -> str | None:
        key = best_question(self.candidates, self.asked)
        if not key:
            for role in self.candidates:
                guess_key = f"guess:{role.name}"
                if guess_key not in self.asked:
                    key = guess_key
                    break
        self.current_question = key
        if key:
            self.asked.add(key)
        return key

    def reject_last_result(self) -> None:
        if not self.last_result_names:
            return
        rejected = self.last_result_names
        self.rejected_names.update(rejected)
        self.candidates = [role for role in self.candidates if role.name not in rejected]
        if not self.candidates:
            self.candidates = [
                role for role in self.all_roles if role.name not in self.rejected_names
            ]
        self.last_result_names = set()
        self.current_question = None
        # A wrong final guess usually means an earlier split was too brittle.
        # Clear the history so the retry can reuse useful questions if needed.
        self.asked.clear()
        self.history.clear()
        self.positive_answer_count = 0
        self.answered_question_count = 0


sessions: dict[int, GuessSession] = {}

MIN_FINAL_ANSWERED_QUESTIONS = 8
MIN_FINAL_POSITIVE_ANSWERS = 3


def primary_team(role: Role) -> str | None:
    for key in TEAM_QUESTION_KEYS:
        if role.features.get(key) is True:
            return key
    return None


def should_delay_final_result(session: GuessSession) -> bool:
    return (
        session.answered_question_count < MIN_FINAL_ANSWERED_QUESTIONS
        or session.positive_answer_count < MIN_FINAL_POSITIVE_ANSWERS
    )


def nearby_candidates_for_more_questions(session: GuessSession, role: Role) -> list[Role]:
    team_key = primary_team(role)
    nearby = []
    for candidate in session.all_roles:
        if candidate.name in session.rejected_names:
            continue
        if candidate.mod != role.mod:
            continue
        if team_key and primary_team(candidate) != team_key:
            continue
        nearby.append(candidate)
    return nearby


def expand_final_candidates_if_needed(session: GuessSession) -> bool:
    if not session.candidates or not should_delay_final_result(session):
        return False

    expanded: list[Role] = []
    seen_names: set[str] = set()
    for role in session.candidates:
        for candidate in nearby_candidates_for_more_questions(session, role):
            if candidate.name in seen_names:
                continue
            seen_names.add(candidate.name)
            expanded.append(candidate)

    if len(expanded) <= len(session.candidates):
        return False
    if best_question(expanded, session.asked) is None:
        return False

    session.candidates = expanded
    return True


def feature_signature(role: Role) -> tuple[tuple[str, bool | None], ...]:
    # Imported data often leaves non-applicable features blank. For final
    # grouping, treat blank like "no" so equivalent cross-mod roles are shown
    # together instead of asking a long tail of one-sided negative questions.
    return tuple((key, role.features.get(key) is True) for key in FEATURE_QUESTIONS)


def grouped_candidate_text(roles: list[Role], limit: int = 10) -> str:
    grouped: dict[tuple[str, tuple[tuple[str, bool | None], ...]], list[Role]] = {}
    for role in roles:
        grouped.setdefault((role.display_name, feature_signature(role)), []).append(role)

    lines = []
    for (display_name, _), items in list(grouped.items())[:limit]:
        mods = " / ".join(sorted({role.mod for role in items}))
        lines.append(f"- {display_name} ({mods})")
    remaining = len(grouped) - limit
    if remaining > 0:
        lines.append(f"ほか {remaining} 種類")
    return "\n".join(lines)


def role_label(role: Role) -> str:
    if role.display_name == role.name:
        return role.display_name
    return f"{role.display_name}"


def quiz_hints_for(role: Role, max_hints: int = 5) -> list[str]:
    priority = [
        "team_crewmate",
        "team_impostor",
        "team_neutral",
        "team_liberal",
        "team_madmate",
        "team_jackal",
        "liberal_fund_power",
        "untargetable_power",
        "modifier_role",
        "nos_role",
        "snr_role",
        "tohk_role",
        "exr_role",
        "nos_modifier_role",
        "buff_modifier_power",
        "debuff_modifier_power",
        "evil_support_power",
        "host_observer_power",
        "plain_role_power",
        "emergency_repair_power",
        "no_task_role",
        "utility_restriction_power",
        "sabotage_repair_restriction_power",
        "limited_kill_power",
        "task_kill_charge_power",
        "ghost_role",
        "nos_ghost_role",
        "soul_vision_power",
        "ghost_crewmate_power",
        "ghost_impostor_power",
        "ghost_neutral_power",
        "can_kill",
        "normal_kill",
        "sheriff_misfire_power",
        "guess_misfire_power",
        "suicide_button_power",
        "serial_suicide_timer_power",
        "gamble_cooldown_power",
        "target_mismatch_suicide_power",
        "vampire_bite_power",
        "blood_stain_power",
        "thrall_creation_power",
        "special_kill",
        "area_instant_kill_power",
        "projectile_barrage_power",
        "multi_hit_kill_power",
        "friendly_fire_option_power",
        "trap_place_power",
        "kill_trap_power",
        "notify_trap_power",
    "vent_trap_power",
        "can_win_alone",
        "oil_douse_win_power",
        "egoist_power",
        "additional_win",
        "extra_win_condition_power",
        "meeting_ability",
        "vote_power",
        "special_vote_power",
        "balance_vote_power",
        "justice_balance_power",
        "balance_self_vote_mode_power",
        "balance_self_target_option_power",
        "balance_restrict_other_abilities_power",
        "dying_message_power",
        "sleep_bomb_power",
        "tofu_fullness_power",
        "chain_shift_power",
        "scarlet_love_power",
        "tyrant_kill_win_power",
        "vanity_sheriff_power",
        "opportunist_survival_power",
        "meeting_kill_power",
        "vote_cancel_power",
        "exile_win",
        "task_based_power",
        "task_progress_display_power",
        "task_rollback_power",
        "global_task_replace_power",
    "trash_cleanup_death_power",
    "muscle_task_pose_power",
        "live_task_win_power",
        "extra_task_power",
        "can_protect",
        "can_investigate",
        "portable_security_power",
        "portable_admin_power",
        "portable_vitals_power",
        "death_cause_power",
        "task_delegation_power",
        "kill_notification_power",
        "kill_flash_power",
        "time_rewind_power",
        "guard_sacrifice_power",
        "counter_power",
        "body_curse_power",
        "body_evolve_power",
        "body_color_power",
        "ghost_body_move_power",
        "ghost_sabotage_repair_power",
        "ghost_photo_power",
        "vent_open_power",
        "sabotage_cooldown_reset_power",
        "ghost_lights_power",
        "ghost_dummy_power",
        "leak_position_power",
        "ghost_obstacle_power",
        "controllable_illusion_power",
        "ghost_stare_win_power",
        "ghost_light_power",
        "corpse_pull_power",
        "ghost_alert_power",
        "corpse_duplicate_power",
        "ghost_possession_vision_power",
        "guardian_angel_judgement_power",
        "ghost_meeting_button_power",
        "ghost_noise_mark_power",
        "ghost_cooldown_reset_power",
        "ghost_role_reveal_power",
        "demon_tracking_power",
        "demon_device_disable_power",
        "demon_vent_open_power",
        "demon_sabotage_power",
        "assisting_angel_power",
        "body_unreportable_power",
        "corpse_guard_charge_power",
        "fake_body_power",
        "fake_player_power",
        "camera_install_power",
    "vent_usage_analysis_power",
    "lantern_place_light_power",
    "drone_control_power",
    "drone_task_reveal_power",
        "vent_block_power",
        "special_vent_power",
        "survival_requirement_power",
        "photo_power",
        "random_teleport_power",
        "mass_teleport_power",
        "teleport_kill_swap_power",
        "self_resurrection_power",
        "magic_circle_power",
        "variable_vote_power",
        "portal_power",
        "meeting_time_power",
        "task_meeting_time_power",
        "meeting_time_steal_power",
        "noncrew_count_power",
        "forced_report_power",
        "jail_power",
        "summon_power",
        "exorcism_power",
        "stress_power",
        "impostor_kill_win_power",
        "sidekick_creation_power",
        "madkiller_creation_power",
        "revenant_creation_power",
        "vent_disguise_move_power",
        "fairy_chain_kill_power",
        "kunai_projectile_power",
        "launch_explosion_power",
        "impostor_task_win_power",
        "solo_impostor_unlock_power",
        "pavlov_owner_dog_power",
        "promotion_power",
        "missionary_power",
        "forced_kill_misfire_power",
        "obsession_power",
        "lovers_attribute_power",
        "shrine_power",
        "mine_power",
        "swallow_power",
        "queen_servant_power",
        "bet_target_win_power",
        "skip_win_power",
        "paint_area_win_power",
        "chimera_creation_power",
        "shadow_object_power",
        "ironmate_power",
        "trash_layer_power",
        "curse_suicide_power",
        "subteam_fallback_power",
        "jackal_subteam_power",
        "mad_teruteru_task_exile_win_power",
        "guard_counter_vision_power",
        "will_report_power",
        "vote_visibility_power",
        "revive_next_turn_power",
        "impostor_judged_crewmate_power",
        "yandere_subteam_power",
        "queen_subteam_power",
        "nonkill_fallback_power",
        "exile_resurrection_power",
        "echo_scan_power",
        "action_detection_power",
        "role_info_power",
        "omniscient_power",
        "public_identity",
        "star_visual_power",
        "body_info_power",
    "corpse_psychometry_power",
        "conversion_power",
        "doll_creation_power",
        "appoint_power",
        "infection_power",
        "partner_power",
        "trilemma_power",
        "lovers_power",
        "combination_role_power",
        "assassin_merlin_power",
        "merlin_info_power",
        "hero_villain_set_power",
        "death_stage_power",
        "crime_scene_power",
        "assistant_report_power",
        "apprentice_investigator_power",
        "graffiti_power",
        "wisp_light_power",
        "same_group_awareness_power",
        "support_target_power",
        "role_guess_kill_power",
        "object_move_power",
        "speed_panel_power",
        "skating_power",
        "vote_swap_power",
        "traitor_cracking_power",
        "sabotage_power",
        "custom_sabotage_win_power",
        "mushroom_power",
        "door_power",
        "room_door_open_power",
        "teleport_power",
        "hijack_vision_power",
        "map_device_fake_power",
        "cooldown_power",
        "collision_kill_power",
        "team_cooldown_boost_power",
        "kill_combo_power",
        "stock_reload_power",
        "role_reveal_boost_power",
        "last_impostor_boost_power",
        "speed_power",
        "vision_power",
        "vision_debuff_power",
        "restriction_power",
        "control_power",
        "ranged_power",
        "ambush_vent_kill_power",
        "second_kill_button_power",
        "bombing_mode_power",
        "object_disguise_power",
        "time_stop_power",
        "weapon_collect_power",
        "punch_launch_power",
        "area_effect",
        "death_trigger",
        "killer_freeze_on_death_power",
        "task_public_reveal_power",
        "blood_trail_power",
        "suicide_risk",
        "vote_zero_power",
        "schrodinger_cat_power",
        "role_change_to_madmate_power",
        "location_stay_win_power",
        "three_pigs_team_power",
        "monster_corpse_creation_power",
        "corpse_nest_power",
        "blackout_body_unlock_power",
    ]
    hints = [
        QUIZ_HINTS[key]
        for key in priority
        if role.features.get(key) is True and key in QUIZ_HINTS
    ]
    if len(hints) <= max_hints:
        return hints or ["No detailed hint is available for this role yet."]

    locked_count = min(2, max_hints)
    locked = hints[:locked_count]
    flexible = hints[locked_count:]
    random.shuffle(flexible)
    return locked + flexible[: max_hints - locked_count]


def build_quiz_embed(answer: Role, choices: list[Role], selected_mod: str | None = None) -> discord.Embed:
    mod_line = f"対象MOD: `{selected_mod}`\n" if selected_mod else "対象MOD: `すべて`\n"
    hints = "\n".join(f"- {hint}" for hint in quiz_hints_for(answer))
    options = "\n".join(
        f"{index + 1}. {role_label(role)}"
        for index, role in enumerate(choices)
    )
    return discord.Embed(
        title="役職クイズ",
        description=(
            f"{mod_line}"
            "次のヒントに当てはまる役職を選んでください。\n\n"
            f"{hints}\n\n"
            f"{options}"
        ),
        color=0x9B59B6,
    )


def build_intro_quiz_embed(answer: Role, choices: list[Role], selected_mod: str | None = None) -> discord.Embed:
    metadata = load_intro_quiz_metadata()
    meta = find_intro_quiz_metadata(answer, metadata)
    mod_meta = metadata.get("mods", {}).get(answer.mod)
    mod_label = mod_meta.get("label") if mod_meta else answer.mod
    intro_text = meta.get("intro_text") if meta else None
    wiki_url = meta.get("wiki_url") if meta else None
    if not wiki_url and mod_meta:
        wiki_url = mod_meta.get("wiki_url")

    mod_line = f"対象MOD: `{selected_mod or mod_label}`\n" if selected_mod or mod_label else "対象MOD: `すべて`\n"
    description = (
        f"{mod_line}"
        "次の短い説明だけで、どの役職か当ててください。\n\n"
    )
    if intro_text:
        description += f"説明: {intro_text}\n\n"
    else:
        description += "説明: 役職の特徴を短く示します。\n\n"
    options = "\n".join(
        f"{index + 1}. {role_label(role)}"
        for index, role in enumerate(choices)
    )
    embed = discord.Embed(
        title="イントロクイズ",
        description=description + options,
        color=0x1ABC9C,
    )
    if wiki_url:
        embed.add_field(name="参考リンク", value=f"[Wiki]({wiki_url})", inline=False)
    else:
        embed.add_field(name="参考リンク", value="未登録", inline=False)
    return embed


def single_group_result(roles: list[Role]) -> discord.Embed | None:
    display_names = {role.display_name for role in roles}
    if len(display_names) != 1:
        return None
    signatures = {feature_signature(role) for role in roles}
    if len(signatures) != 1:
        return None
    display_name = next(iter(display_names))
    mods = " / ".join(sorted({role.mod for role in roles}))
    return discord.Embed(
        title="役職当て",
        description=f"たぶん、あなたが思い浮かべた役職は **{display_name}** です。\nMOD: `{mods}`",
        color=0x2ECC71,
    )


def single_group_roles(roles: list[Role]) -> list[Role] | None:
    display_names = {role.display_name for role in roles}
    if len(display_names) != 1:
        return None
    signatures = {feature_signature(role) for role in roles}
    if len(signatures) != 1:
        return None
    return roles


def indistinguishable_result(roles: list[Role]) -> discord.Embed | None:
    if len(roles) <= 1:
        return None
    signatures = {feature_signature(role) for role in roles}
    if len(signatures) != 1:
        return None
    return discord.Embed(
        title="役職当て",
        description=(
            "ここから先は、今の役職データだけでは区別できません。\n"
            "候補はこのあたりです。\n"
            f"{grouped_candidate_text(roles)}"
        ),
        color=0xF1C40F,
    )


def session_embed(session: GuessSession) -> discord.Embed:
    session.last_result_names = set()
    if len(session.candidates) == 0:
        return discord.Embed(
            title="役職当て",
            description=(
                "候補がなくなりました。役職データが足りないか、どこかの回答が違うかもしれません。\n"
                "一つ前に戻るか、もう一度 `/guess` で最初から試してください。"
            ),
            color=0xE74C3C,
        )
    if (
        session.positive_answer_count == 0
        and len(session.asked) >= 6
        and len(session.candidates) <= 3
    ):
        return discord.Embed(
            title="役職当て",
            description=(
                "ここまで全て「いいえ」寄りの回答なので、該当役職がデータに無いか、"
                "どこかの回答が違う可能性が高いです。\n"
                "一つ前に戻るか、もう一度 `/guess` で最初から試してください。"
            ),
            color=0xE67E22,
        )

    expand_final_candidates_if_needed(session)
    final_result_allowed = not should_delay_final_result(session)

    grouped_roles = single_group_roles(session.candidates)
    if grouped_roles and final_result_allowed:
        session.last_result_names = {role.name for role in grouped_roles}
        return single_group_result(grouped_roles)

    indistinguishable = indistinguishable_result(session.candidates)
    if indistinguishable:
        return indistinguishable

    if len(session.candidates) == 1 and final_result_allowed:
        role = session.candidates[0]
        session.last_result_names = {role.name}
        name_line = f"**{role.display_name}**"
        if role.display_name != role.name:
            name_line += f" (`{role.name}`)"
        return discord.Embed(
            title="役職当て",
            description=f"たぶん、あなたが思い浮かべた役職は {name_line} です。\nMOD: `{role.mod}`",
            color=0x2ECC71,
        )

    key = session.current_question or session.next_question()
    if not key:
        return discord.Embed(
            title="役職当て",
            description=f"候補をすべて確認しました。残っている候補はこのあたりです。\n{grouped_candidate_text(session.candidates)}",
            color=0xF1C40F,
        )

    if key.startswith("guess:"):
        guessed_name = key.removeprefix("guess:")
        role = next((role for role in session.candidates if role.name == guessed_name), None)
        if role:
            name_line = f"**{role.display_name}**"
            if role.display_name != role.name:
                name_line += f" (`{role.name}`)"
            return discord.Embed(
                title="役職当て",
                description=(
                    f"あなたが思い浮かべた役職は {name_line} ですか？\n"
                    f"MOD: `{role.mod}`\n\n"
                    f"残り候補: **{len(session.candidates)}** 件"
                ),
                color=0x2ECC71,
            )

    mod_line = f"対象MOD: `{session.selected_mod}`\n" if session.selected_mod else "対象MOD: `すべて`\n"
    embed = discord.Embed(
        title="役職当て",
        description=(
            mod_line +
            f"{FEATURE_QUESTIONS[key]}\n\n"
            f"残り候補: **{len(session.candidates)}** 件"
        ),
        color=0x3498DB,
    )
    embed.set_footer(text="質問の意味や陣営名が分からない、設定次第で変わる、どちらとも言えない時は「どちらでもない/不明」を選んでください。")
    return embed


def set_back_button_disabled(view: discord.ui.View, disabled: bool) -> None:
    for item in view.children:
        if isinstance(item, discord.ui.Button) and item.label == "戻る":
            item.disabled = disabled


class GuessView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        session = sessions.get(user_id)
        set_back_button_disabled(self, not (session and session.can_go_back()))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このゲームを始めた人だけが回答できます。", ephemeral=True)
        return False

    async def answer(self, interaction: discord.Interaction, value: bool | None) -> None:
        session = sessions.get(self.user_id)
        if not session:
            await interaction.response.edit_message(
                embed=discord.Embed(title="役職当て", description="このゲームは終了しています。", color=0x95A5A6),
                view=None,
            )
            return

        session.push_history()
        session.apply_answer(value)
        session.current_question = None
        embed = session_embed(session)
        if session.last_result_names:
            await interaction.response.edit_message(embed=embed, view=GuessResultView(self.user_id))
            return
        finished = (
            indistinguishable_result(session.candidates) is not None
            or "候補がなくなりました" in embed.description
            or "該当役職がデータに無い" in embed.description
            or "候補をすべて確認しました" in embed.description
        )
        if finished:
            if session.can_go_back():
                await interaction.response.edit_message(embed=embed, view=GuessBackView(self.user_id))
                return
            sessions.pop(self.user_id, None)
            await interaction.response.edit_message(embed=embed, view=None)
            return
        await interaction.response.edit_message(embed=embed, view=GuessView(self.user_id))

    @discord.ui.button(label="はい", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, True)

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, False)

    @discord.ui.button(label="どちらでもない/不明", style=discord.ButtonStyle.secondary)
    async def unknown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.answer(interaction, None)

    @discord.ui.button(label="戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await go_back_one_question(interaction, self.user_id)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions.pop(self.user_id, None)
        await interaction.response.edit_message(
            embed=discord.Embed(title="役職当て", description="ゲームを中止しました。", color=0x95A5A6),
            view=None,
        )


class GuessResultView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        session = sessions.get(user_id)
        set_back_button_disabled(self, not (session and session.can_go_back()))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このゲームを始めた人だけが操作できます。", ephemeral=True)
        return False

    @discord.ui.button(label="正解", style=discord.ButtonStyle.success)
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions.pop(self.user_id, None)
        await interaction.response.edit_message(
            embed=discord.Embed(title="役職当て", description="当たってよかったです。ゲームを終了しました。", color=0x2ECC71),
            view=None,
        )

    @discord.ui.button(label="違う、続ける", style=discord.ButtonStyle.danger)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = sessions.get(self.user_id)
        if not session:
            await interaction.response.edit_message(
                embed=discord.Embed(title="役職当て", description="このゲームは終了しています。", color=0x95A5A6),
                view=None,
            )
            return

        session.reject_last_result()
        embed = session_embed(session)
        if len(session.candidates) == 0:
            sessions.pop(self.user_id, None)
            await interaction.response.edit_message(embed=embed, view=None)
            return
        view = guess_view_for_session(session, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await go_back_one_question(interaction, self.user_id)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions.pop(self.user_id, None)
        await interaction.response.edit_message(
            embed=discord.Embed(title="役職当て", description="ゲームを中止しました。", color=0x95A5A6),
            view=None,
        )


class GuessBackView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        session = sessions.get(user_id)
        set_back_button_disabled(self, not (session and session.can_go_back()))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このゲームを始めた人だけが操作できます。", ephemeral=True)
        return False

    @discord.ui.button(label="戻る", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await go_back_one_question(interaction, self.user_id)

    @discord.ui.button(label="中止", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions.pop(self.user_id, None)
        await interaction.response.edit_message(
            embed=discord.Embed(title="役職当て", description="ゲームを中止しました。", color=0x95A5A6),
            view=None,
        )


def guess_view_for_session(session: GuessSession, user_id: int) -> discord.ui.View | None:
    if session.last_result_names:
        return GuessResultView(user_id)
    if session.current_question:
        return GuessView(user_id)
    if session.can_go_back():
        return GuessBackView(user_id)
    return None


async def go_back_one_question(interaction: discord.Interaction, user_id: int) -> None:
    session = sessions.get(user_id)
    if not session or not session.go_back():
        await interaction.response.send_message("戻れる質問がありません。", ephemeral=True)
        return
    embed = session_embed(session)
    await interaction.response.edit_message(
        embed=embed,
        view=guess_view_for_session(session, user_id),
    )


class QuizChoiceButton(discord.ui.Button):
    def __init__(self, index: int, role: Role):
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.primary)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, QuizView):
            return
        await view.answer(interaction, self.role)


class QuizView(discord.ui.View):
    def __init__(self, user_id: int, answer: Role, choices: list[Role]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.answer_role = answer
        for index, role in enumerate(choices):
            self.add_item(QuizChoiceButton(index, role))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("このクイズを始めた人だけが回答できます。", ephemeral=True)
        return False

    async def answer(self, interaction: discord.Interaction, selected: Role) -> None:
        correct = selected.name == self.answer_role.name
        color = 0x2ECC71 if correct else 0xE74C3C
        result = "正解です！" if correct else "不正解です。"
        metadata = load_intro_quiz_metadata()
        quiz_meta = find_intro_quiz_metadata(self.answer_role, metadata)
        mod_meta = metadata.get("mods", {}).get(self.answer_role.mod)
        wiki_url = quiz_meta.get("wiki_url") if quiz_meta else None
        if not wiki_url and mod_meta:
            wiki_url = mod_meta.get("wiki_url")
        embed = discord.Embed(
            title="役職クイズ",
            description=(
                f"{result}\n\n"
                f"答え: **{role_label(self.answer_role)}**\n"
                f"MOD: `{self.answer_role.mod}`\n"
                f"あなたの回答: **{role_label(selected)}**"
            ),
            color=color,
        )
        if wiki_url:
            embed.add_field(name="参考リンク", value=f"[Wiki]({wiki_url})", inline=False)
        else:
            embed.add_field(name="参考リンク", value="未登録", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class RoleGuesserBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        synced = await self.tree.sync()
        print(f"Roles Guesser global slash commands synced: {len(synced)}", flush=True)
        if TARGET_GUILD_ID:
            guild = discord.Object(id=TARGET_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            guild_synced = await self.tree.sync(guild=guild)
            print(
                f"Roles Guesser guild slash commands synced: {len(guild_synced)} to {GUILD_ID}",
                flush=True,
            )


role_bot = RoleGuesserBot()


@role_bot.event
async def on_ready():
    print(f"Role Guesser ready: {role_bot.user} ({role_bot.user.id})", flush=True)


async def mod_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    mods = sorted({role.mod for role in load_roles()})
    current_lower = current.lower()
    choices = [
        app_commands.Choice(name=mod, value=mod)
        for mod in mods
        if current_lower in mod.lower()
    ]
    return choices[:25]


async def start_guess_session(interaction: discord.Interaction, mod: str | None = None):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    selected_mod = normalize_mod_name(mod) if mod else ""
    if selected_mod:
        matched_roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
        if not matched_roles:
            mods = ", ".join(sorted({role.mod for role in roles}))
            await interaction.response.send_message(
                f"`{selected_mod}` は登録されていません。\n登録MOD: {mods or 'なし'}",
                ephemeral=True,
            )
            return
        roles = matched_roles
        selected_mod = roles[0].mod
    else:
        selected_mod = None

    session = GuessSession(interaction.user.id, roles, selected_mod)
    sessions[interaction.user.id] = session
    embed = session_embed(session)
    view: discord.ui.View = GuessResultView(interaction.user.id) if session.last_result_names else GuessView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)


@role_bot.tree.command(name="guess", description="Among Us系Modの役職当てを始めます")
@app_commands.describe(mod="絞り込むMOD名。未指定なら全MODから当てます")
@app_commands.autocomplete(mod=mod_autocomplete)
async def guess(interaction: discord.Interaction, mod: str | None = None):
    await start_guess_session(interaction, mod)


@role_bot.tree.command(name="quiz", description="Among Us系Modの通常クイズを出します")
@app_commands.describe(mod="出題するMOD名。必須です")
@app_commands.autocomplete(mod=mod_autocomplete)
async def quiz(interaction: discord.Interaction, mod: str):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    selected_mod = normalize_mod_name(mod) if mod else ""
    if not selected_mod:
        await interaction.response.send_message("クイズは MOD 指定必須です。対象の MOD を指定してください。", ephemeral=True)
        return

    matched_roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
    if not matched_roles:
        mods = ", ".join(sorted({role.mod for role in roles}))
        await interaction.response.send_message(
            f"`{selected_mod}` は登録されていません。\n登録MOD: {mods or 'なし'}",
            ephemeral=True,
        )
        return
    roles = matched_roles
    selected_mod = roles[0].mod

    quiz_roles = [role for role in roles if role.mod == selected_mod]
    if len(quiz_roles) < 2:
        await interaction.response.send_message("クイズを作るには、候補役職が2件以上必要です。", ephemeral=True)
        return

    answer = random.choice(quiz_roles)
    distractors = [role for role in quiz_roles if role.name != answer.name]
    choice_count = min(4, len(quiz_roles))
    choices = random.sample(distractors, k=choice_count - 1) + [answer]
    random.shuffle(choices)

    await interaction.response.send_message(
        embed=build_quiz_embed(answer, choices, selected_mod),
        view=QuizView(interaction.user.id, answer, choices),
    )


@role_bot.tree.command(name="introquiz", description="Among Us系Modのイントロクイズを出します")
@app_commands.describe(mod="出題するMOD名。必須です")
@app_commands.autocomplete(mod=mod_autocomplete)
async def introquiz(interaction: discord.Interaction, mod: str):
    roles = load_roles()
    if not roles:
        await interaction.response.send_message("役職データがまだありません。", ephemeral=True)
        return

    selected_mod = normalize_mod_name(mod) if mod else ""
    if not selected_mod:
        await interaction.response.send_message("イントロクイズは MOD 指定必須です。対象の MOD を指定してください。", ephemeral=True)
        return

    matched_roles = [role for role in roles if role.mod.lower() == selected_mod.lower()]
    if not matched_roles:
        mods = ", ".join(sorted({role.mod for role in roles}))
        await interaction.response.send_message(
            f"`{selected_mod}` は登録されていません。\n登録MOD: {mods or 'なし'}",
            ephemeral=True,
        )
        return
    roles = matched_roles
    selected_mod = roles[0].mod

    intro_roles = filter_roles_for_intro_quiz(roles, selected_mod)
    if len(intro_roles) < 2:
        await interaction.response.send_message("イントロクイズを作るには、対象MODに2件以上の役職が必要です。", ephemeral=True)
        return

    unique_roles = {}
    for role in intro_roles:
        unique_roles.setdefault((role.display_name, feature_signature(role)), role)
    quiz_roles = list(unique_roles.values())
    if len(quiz_roles) < 2:
        await interaction.response.send_message("クイズを作るには、候補役職が2件以上必要です。", ephemeral=True)
        return

    answer = random.choice(quiz_roles)
    distractors = [role for role in quiz_roles if role.name != answer.name]
    choice_count = min(4, len(quiz_roles))
    choices = random.sample(distractors, k=choice_count - 1) + [answer]
    random.shuffle(choices)

    await interaction.response.send_message(
        embed=build_intro_quiz_embed(answer, choices, selected_mod),
        view=QuizView(interaction.user.id, answer, choices),
    )


@role_bot.tree.command(name="roles", description="登録されている役職数を表示します")
async def roles(interaction: discord.Interaction):
    loaded_roles = load_roles()
    mods = sorted({role.mod for role in loaded_roles})
    await interaction.response.send_message(
        f"登録役職: **{len(loaded_roles)}** 件\n登録MOD: {', '.join(mods) or 'なし'}",
        ephemeral=True,
    )


@role_bot.tree.command(name="help", description="Roles Guesserの使い方を表示します")
async def help(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(
            title="Roles Guesser ヘルプ",
            description=(
                "以下のコマンドで役職当て・クイズを遊べます。\n"
                "`mod` は MOD 名を指定してください。\n"
                "`/guess` は質問に答えて役職を当てるモードです。\n"
                "`/quiz` は通常の役職クイズです。\n"
                "`/introquiz` は `intro_quiz.json` に登録された短い説明とリンクを使うイントロクイズです。\n"
                "`/roles` は登録済みの役職数と MOD を表示します。"
            ),
            color=0x3498DB,
        ),
        ephemeral=True,
    )


async def start_role_guesser_bot() -> None:
    if not ROLE_GUESSER_TOKEN:
        print("ROLE_GUESSER_TOKEN is not set; Role Guesser bot skipped.", flush=True)
        return
    try:
        await role_bot.start(ROLE_GUESSER_TOKEN)
    except Exception as exc:
        print(f"Role Guesser bot failed to start: {type(exc).__name__}: {exc}", flush=True)
