from __future__ import annotations

import csv
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
    "buff_modifier_power": "?????????????????????????",
    "debuff_modifier_power": "????????????????????????????",
    "evil_support_power": "マッドメイトやジャッカルフレンズなど、別陣営を助ける補助・狂人系役職ですか？",
    "host_observer_power": "ホスト専用の観戦・GM系役職ですか？",
    "plain_role_power": "特殊能力はほぼなく、共通設定や視界だけが変わる役職ですか？",
    "emergency_repair_power": "サボタージュを即座に修理する能力がありますか？",
    "no_task_role": "タスクを持たない役職ですか？",
    "utility_restriction_power": "アドミン・バイタル・カメラ・緊急会議などの機器使用が制限されますか？",
    "sabotage_repair_restriction_power": "特定のサボタージュ修理ができない役職/属性ですか？",
    "limited_kill_power": "キル可能回数に上限がありますか？",
    "task_kill_charge_power": "タスク進捗でキル回数やキルCTが変わりますか？",
    "can_kill": "自分の操作で誰かを死亡させる能力がありますか？",
    "normal_kill": "普通のキルボタンでキルする役職ですか？",
    "special_kill": "普通のキルボタン以外で死亡させる能力がありますか？（例: 爆破、推測、ビーム、罠、会議キル）",
    "target_power": "特定の相手を選ぶ能力ですか？（例: 指名、恋人化、投獄、ターゲット指定）",
    "target_kill_power": "特定の相手を殺す/死なせることが目的や能力条件ですか？（例: 賞金首、復讐対象、推測キル）",
    "guard_piercing_power": "ガードやシールドを貫通するキル能力がありますか？",
    "kill_range_modifier_power": "??????????????????????",
    "kill_power_boost_power": "?????????????????????????????",
    "wave_cannon_power": "波動砲・レーザー・ビームのような直線攻撃ですか？",
    "uses_vent": "その役職はベントを使えますか？",
    "can_win_alone": "その役職は単独勝利できますか？",
    "additional_win": "他陣営の勝利に便乗して追加勝利しますか？",
    "extra_win_condition_power": "?????????????????????",
    "can_protect": "誰かを守る能力がありますか？（例: ガード、バリア、キル防止）",
    "can_investigate": "情報を調べる能力がありますか？（例: 役職/陣営/死因/位置を調査）",
    "portable_security_power": "どこでもセキュリティカメラやドアログを見られますか？",
    "portable_admin_power": "どこでもアドミン情報を見られますか？",
    "task_delegation_power": "他人のタスクを肩代わり・取得できますか？",
    "kill_notification_power": "キル発生時に時間・方角・部屋などの通知を受けますか？",
    "time_rewind_power": "キルを無効化して時間や移動を巻き戻しますか？",
    "guard_sacrifice_power": "他人を守るために自分が身代わりで死亡しますか？",
    "counter_power": "攻撃を防いで反撃や一時的なキル権を得ますか？",
    "body_curse_power": "死体に使ってキラーにクールペナルティ等を与えますか？",
    "camera_install_power": "カメラや監視装置を設置できますか？",
    "vent_block_power": "ベントを封鎖・使用不能にできますか？",
    "survival_requirement_power": "生存やタスク進捗が自分の勝利に影響しますか？",
    "photo_power": "写真や記録として位置情報を後で確認できますか？",
    "random_teleport_power": "対象をランダムな場所や別プレイヤーの位置へ飛ばしますか？",
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
    "task_progress_display_power": "????????????????????",
    "extra_task_power": "追加タスクや専用タスクが割り当てられますか？",
    "death_trigger": "自分や対象が死亡した時に能力が発動しますか？（例: 道連れ、後追い、通知、変化）",
    "blood_trail_power": "??????????????????????????",
    "scheduled_death": "決まった条件やタイミングで自動的に死亡しますか？",
    "ghost_role": "死亡後・幽霊状態で使う役職ですか？",
    "ghost_power": "幽霊や死亡済みプレイヤーに関わる能力がありますか？（例: 霊視、蘇生、幽霊能力）",
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
    "cursor_reveal_power": "????????????????????????",
    "fake_identity": "他人から別陣営・別役職・別人のように見える能力ですか？",
    "dummy_power": "ダミーや分身を表示する能力がありますか？",
    "body_info_power": "死体・死因・死亡位置に関する情報を得られますか？",
    "body_clear_power": "死体を消したり処理したりできますか？（例: 食べる、掃除、蘇生用に消す）",
    "body_move_power": "死体を運んだり別の場所へ動かしたりできますか？",
    "corpse_consumption_power": "死体を食べる・消すことで勝利や能力に関わりますか？",
    "delayed_kill": "能力を使ってから遅れて死亡しますか？（例: 呪い、時限爆弾、後で発動するキル）",
    "bomb_power": "爆弾を付与・設置して爆発させる能力ですか？",
    "marker_power": "マーカーや地点を指定して範囲を作る能力ですか？",
    "disguise_or_invisible": "変身・透明化・姿の偽装ができますか？",
    "appearance_shuffle_power": "???????????????????????????",
    "area_effect": "周囲や部屋全体に影響しますか？（例: 範囲キル、爆発、全員の移動制限）",
    "sabotage_power": "サボタージュに関わる特別な能力がありますか？（例: 独自サボ、即修理、サボクール操作）",
    "lights_sabotage_power": "停電サボタージュに特化した能力や制限がありますか？",
    "critical_sabotage_power": "リアクター・O2などの緊急サボタージュに特化した能力や制限がありますか？",
    "door_power": "ドアを開閉・一括開放・妨害する能力がありますか？",
    "room_door_open_power": "??????????????????????????",
    "specific_door_power": "特定の場所や設備のドアだけに作用しますか？（例: トイレ、特定部屋）",
    "revenge_kill": "自分を殺した相手を道連れにできますか？",
    "suicide_risk": "能力の代償や条件で自滅する可能性がありますか？",
    "conversion_power": "他人の役職・陣営・状態を変えますか？（例: サイドキック化、感染、投獄、蘇生）",
    "appoint_power": "対象をシェリフなどの特定役職に任命・転職させますか？",
    "infection_power": "感染や拡散で他人の状態を広げますか？",
    "partner_power": "特定の相方・主人・対象とペアやチームになりますか？",
    "trilemma_power": "3??????????????2???????????????",
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
    "vision_debuff_power": "????????????????????",
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
    "impostor_kill_win_power": "インポスターにキルされることが勝利条件に関わりますか？",
    "sidekick_creation_power": "任意の相手をサイドキックにして同陣営へ引き込めますか？",
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
    "traitor_cracking_power": "キル後にアドミン・カメラ・バイタルを遠隔で順番に使えますか？",
    "corpse_guard_charge_power": "死体を処理して誰かを守る回数を増やしますか？",
    "ambush_vent_kill_power": "ベント中やベント付近から特殊キルを行いますか？",
    "second_kill_button_power": "通常キルとは別の二つ目のキルボタンを持ちますか？",
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
    "killer_freeze_on_death_power": "キルされた時、キルした相手を一定時間動けなくしますか？",
    "oil_douse_win_power": "全生存者にオイルを塗り、ベントに入ることで勝利しますか？",
    "egoist_power": "インポスターを認識しつつ、インポスター全滅後に勝利を狙いますか？",
    "pavlov_owner_dog_power": "オーナーが犬を指名し、犬がキル役として行動する役職ですか？",
}

QUIZ_HINTS = {
    "team_crewmate": "クルー陣営の役職です。",
    "team_impostor": "インポスター陣営の役職です。",
    "team_neutral": "第三陣営の役職です。",
    "team_liberal": "リベラル陣営の役職です。リーダーを中心に、資金を貯めて勝利を目指します。",
    "team_madmate": "マッドメイト陣営・狂人系チームです。",
    "team_jackal": "ジャッカル陣営です。",
    "modifier_role": "元の役職に追加される役職・属性です。",
    "evil_support_power": "別陣営を助ける補助・狂人系役職です。",
    "host_observer_power": "ホスト専用の観戦・GM系役職です。",
    "plain_role_power": "特殊能力がほぼない基本役職です。",
    "emergency_repair_power": "緊急タスクやサボを即修理できます。",
    "no_task_role": "タスクを持ちません。",
    "utility_restriction_power": "機器や緊急会議の使用が制限されます。",
    "limited_kill_power": "キル可能回数に上限があります。",
    "task_kill_charge_power": "タスク進捗でキル回数やCTが変わります。",
    "can_kill": "キル能力に関わります。",
    "normal_kill": "通常キルに関わります。",
    "special_kill": "特殊キルに関わります。",
    "target_power": "特定の対象を選ぶ能力があります。",
    "target_kill_power": "指定対象のキルが能力や勝利条件に関わります。",
    "guard_piercing_power": "ガードや防御を貫通する能力に関わります。",
    "wave_cannon_power": "波動砲やビームに関わります。",
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
    "ghost_power": "幽霊や死亡済みプレイヤーに関わります。",
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
    "vote_power": "投票や会議結果に干渉します。",
    "exile_win": "追放されることが勝利条件に関わります。",
    "tracking_power": "位置や移動を追跡できます。",
    "role_info_power": "役職や陣営情報を知る能力があります。",
    "omniscient_power": "全員の役職を常に見ることができます。",
    "public_identity": "存在や役職が他人に分かります。",
    "fake_identity": "別陣営や別役職のように見える要素があります。",
    "dummy_power": "ダミーや分身を表示します。",
    "body_info_power": "死体・死因・死亡位置に関わります。",
    "body_clear_power": "死体を消したり処理したりできます。",
    "body_move_power": "死体を運んだり動かしたりできます。",
    "corpse_consumption_power": "死体の捕食や消去が勝利・能力に関わります。",
    "delayed_kill": "遅延キルや間接キルに関わります。",
    "bomb_power": "爆弾の付与・設置・爆発に関わります。",
    "marker_power": "マーカーや地点指定による範囲能力に関わります。",
    "disguise_or_invisible": "変身・透明化・姿の偽装に関わります。",
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
    "impostor_kill_win_power": "インポスターにキルされることが勝利に関わります。",
    "sidekick_creation_power": "相手をサイドキック化できます。",
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
    "traitor_cracking_power": "キル後のクラッキングに関わります。",
    "corpse_guard_charge_power": "死体処理で防御回数を増やします。",
    "ambush_vent_kill_power": "ベントを使った奇襲キルに関わります。",
    "second_kill_button_power": "二つ目のキルボタンを持ちます。",
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
    "buff_modifier_power": "??????????????",
    "debuff_modifier_power": "????????????????",
    "sabotage_repair_restriction_power": "特定のサボタージュ修理が制限されます。",
    "kill_range_modifier_power": "???????????",
    "kill_power_boost_power": "??????????????",
    "extra_win_condition_power": "?????????????",
    "task_progress_display_power": "????????????",
    "blood_trail_power": "???????????????????",
    "cursor_reveal_power": "????????????????",
    "appearance_shuffle_power": "?????????????",
    "room_door_open_power": "???????????????",
    "trilemma_power": "3???????????????",
    "vision_debuff_power": "???????????????",
    "vote_zero_power": "投票数が0票になります。",
    "task_meeting_time_power": "タスク完了で会議時間が延びます。",
    "killer_freeze_on_death_power": "キルした相手を拘束します。",
    "oil_douse_win_power": "全員にオイルを塗ってベントに入る勝利条件です。",
    "egoist_power": "インポスターを認識するが、インポスターとは競合します。",
    "pavlov_owner_dog_power": "オーナーが犬を作り、犬はキル能力を持ちます。",
}


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
    "host_observer_power": 1.6,
    "can_kill": 1.5,
    "can_win_alone": 1.5,
    "meeting_ability": 1.2,
    "vote_power": 1.2,
    "special_vote_power": 1.35,
    "balance_vote_power": 2.2,
    "sidekick_creation_power": 1.7,
    "pavlov_owner_dog_power": 2.2,
    "oil_douse_win_power": 2.0,
    "egoist_power": 2.0,
    "forced_kill_misfire_power": 1.8,
    "lovers_power": 1.6,
    "queen_servant_power": 1.7,
    "chimera_creation_power": 1.7,
    "trash_layer_power": 1.7,
    "weapon_collect_power": 1.6,
    "ghost_crewmate_power": 1.5,
    "ghost_impostor_power": 1.5,
    "ghost_neutral_power": 1.5,
}


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


def best_question(candidates: list[Role], asked: set[str]) -> str | None:
    scored: list[tuple[float, str]] = []
    for key in FEATURE_QUESTIONS:
        if key in asked:
            continue
        yes_count = sum(1 for role in candidates if role.features.get(key) is True)
        no_count = sum(1 for role in candidates if role.features.get(key) is False)
        known_count = yes_count + no_count
        if known_count == 0:
            continue
        balance = min(yes_count, no_count)
        coverage_bonus = known_count * 0.05
        one_sided_bonus = 0.25 if yes_count == 0 or no_count == 0 else 0
        score = balance + coverage_bonus + one_sided_bonus + priority_bonus(key)
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
        self.history: list[
            tuple[list[Role], set[str], str | None, set[str], set[str]]
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
        ) = self.history.pop()
        return True

    def apply_answer(self, answer: bool | None) -> None:
        if not self.current_question:
            return
        key = self.current_question
        if key.startswith("guess:"):
            if answer is None:
                return
            guessed_name = key.removeprefix("guess:")
            if answer:
                self.candidates = [role for role in self.candidates if role.name == guessed_name]
            else:
                self.candidates = [role for role in self.candidates if role.name != guessed_name]
            return

        matched = []
        for role in self.candidates:
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


sessions: dict[int, GuessSession] = {}


def feature_signature(role: Role) -> tuple[tuple[str, bool | None], ...]:
    return tuple((key, role.features.get(key)) for key in FEATURE_QUESTIONS)


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
        "ghost_crewmate_power",
        "ghost_impostor_power",
        "ghost_neutral_power",
        "can_kill",
        "normal_kill",
        "special_kill",
        "can_win_alone",
        "oil_douse_win_power",
        "egoist_power",
        "additional_win",
        "extra_win_condition_power",
        "meeting_ability",
        "vote_power",
        "special_vote_power",
        "balance_vote_power",
        "meeting_kill_power",
        "vote_cancel_power",
        "exile_win",
        "task_based_power",
        "task_progress_display_power",
        "task_rollback_power",
        "global_task_replace_power",
        "live_task_win_power",
        "extra_task_power",
        "can_protect",
        "can_investigate",
        "portable_security_power",
        "portable_admin_power",
        "task_delegation_power",
        "kill_notification_power",
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
        "vent_block_power",
        "special_vent_power",
        "survival_requirement_power",
        "photo_power",
        "random_teleport_power",
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
        "yandere_subteam_power",
        "queen_subteam_power",
        "nonkill_fallback_power",
        "exile_resurrection_power",
        "echo_scan_power",
        "action_detection_power",
        "role_info_power",
        "omniscient_power",
        "body_info_power",
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
        "blood_trail_power",
        "suicide_risk",
        "vote_zero_power",
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
            description="候補がなくなりました。役職データが足りないか、どこかの回答が違うかもしれません。",
            color=0xE74C3C,
        )

    grouped_roles = single_group_roles(session.candidates)
    if grouped_roles:
        session.last_result_names = {role.name for role in grouped_roles}
        return single_group_result(grouped_roles)

    indistinguishable = indistinguishable_result(session.candidates)
    if indistinguishable:
        return indistinguishable

    if len(session.candidates) == 1:
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
        await interaction.response.edit_message(embed=embed, view=None)


class RoleGuesserBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


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


@role_bot.tree.command(name="guess", description="Among Us系Modの役職当てを始めます")
@app_commands.describe(mod="絞り込むMOD名。未指定なら全MODから当てます")
@app_commands.autocomplete(mod=mod_autocomplete)
async def guess(interaction: discord.Interaction, mod: str | None = None):
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


@role_bot.tree.command(name="quiz", description="Among Us系Modの役職クイズを出します")
@app_commands.describe(mod="出題するMOD名。未指定なら全MODから出題します")
@app_commands.autocomplete(mod=mod_autocomplete)
async def quiz(interaction: discord.Interaction, mod: str | None = None):
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

    unique_roles = {}
    for role in roles:
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
        embed=build_quiz_embed(answer, choices, selected_mod),
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


async def start_role_guesser_bot() -> None:
    if not ROLE_GUESSER_TOKEN:
        print("ROLE_GUESSER_TOKEN is not set; Role Guesser bot skipped.", flush=True)
        return
    try:
        await role_bot.start(ROLE_GUESSER_TOKEN)
    except Exception as exc:
        print(f"Role Guesser bot failed to start: {type(exc).__name__}: {exc}", flush=True)
