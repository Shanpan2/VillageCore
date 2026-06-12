import csv
from pathlib import Path
from collections import Counter

path = Path('role_guesser/data/roles.csv')
rows = list(csv.DictReader(path.open('r', encoding='utf-8-sig', newline='')))

feature_keys = [
 'team_crewmate','team_impostor','team_neutral','team_liberal','team_madmate','team_jackal','modifier_role','nos_role','snr_role','tohk_role','exr_role','nos_modifier_role','buff_modifier_power','debuff_modifier_power','evil_support_power','host_observer_power','host_only_power','non_counting_power','plain_role_power','emergency_repair_power','no_task_role','utility_restriction_power','sabotage_repair_restriction_power','limited_kill_power','task_kill_charge_power','can_kill','normal_kill','sheriff_misfire_power','guess_misfire_power','suicide_button_power','serial_suicide_timer_power','gamble_cooldown_power','target_mismatch_suicide_power','special_kill','trap_place_power','kill_trap_power','notify_trap_power','vent_trap_power','target_power','target_kill_power','guard_piercing_power','kill_range_modifier_power','kill_power_boost_power','wave_cannon_power','area_instant_kill_power','projectile_barrage_power','multi_hit_kill_power','friendly_fire_option_power','uses_vent','can_win_alone','additional_win','extra_win_condition_power','can_protect','can_investigate','portable_security_power','portable_admin_power','portable_vitals_power','death_cause_power','task_delegation_power','kill_notification_power','kill_flash_power','time_rewind_power','guard_sacrifice_power','counter_power','body_curse_power','camera_install_power','vent_usage_analysis_power','lantern_place_light_power','drone_control_power','drone_task_reveal_power','vent_block_power','survival_requirement_power','photo_power','random_teleport_power','mass_teleport_power','teleport_kill_swap_power','self_resurrection_power','variable_vote_power','portal_power','meeting_time_power','noncrew_count_power','forced_report_power','jail_power','summon_power','exorcism_power','stress_power','exile_resurrection_power','echo_scan_power','action_detection_power','compare_power','meeting_ability','meeting_message','has_tasks','task_based_power','task_progress_display_power','extra_task_power','death_trigger','blood_trail_power','scheduled_death','ghost_role','nos_ghost_role','ghost_power','soul_vision_power','ghost_crewmate_power','ghost_impostor_power','ghost_neutral_power','ghost_body_move_power','ghost_sabotage_repair_power','ghost_photo_power','vent_open_power','sabotage_cooldown_reset_power','ghost_lights_power','ghost_dummy_power','leak_position_power','ghost_obstacle_power','controllable_illusion_power','ghost_stare_win_power','ghost_light_power','corpse_pull_power','ghost_alert_power','corpse_duplicate_power','ghost_possession_vision_power','guardian_angel_judgement_power','ghost_meeting_button_power','ghost_noise_mark_power','ghost_cooldown_reset_power','ghost_role_reveal_power','demon_tracking_power','demon_device_disable_power','demon_vent_open_power','demon_sabotage_power','assisting_angel_power','vote_power','exile_win','tracking_power','role_info_power','omniscient_power','public_identity','star_visual_power','cursor_reveal_power','fake_identity','dummy_power','body_info_power','corpse_psychometry_power','body_clear_power','body_move_power','corpse_consumption_power','delayed_kill','vampire_bite_power','blood_stain_power','thrall_creation_power','collision_kill_power','bomb_power','marker_power','disguise_or_invisible','invisibility_power','shapeshift_power','global_camouflage_power','growth_size_power','appearance_shuffle_power','area_effect','sabotage_power','lights_sabotage_power','critical_sabotage_power','door_power','room_door_open_power','specific_door_power','revenge_kill','suicide_risk','conversion_power','appoint_power','infection_power','partner_power','trilemma_power','lovers_power','lovers_attribute_power','alignment_shift_power','control_power','restriction_power','ranged_power','wall_piercing_power','teleport_power','cooldown_power','speed_power','movement_power','stationary_death_power','environmental_death_power','report_power','vision_power','vision_debuff_power','swap_power','fate_swap_power','dance_power','prophecy_power','extra_vote_power','special_vote_power','body_evolve_power','body_color_power','fake_body_power','fake_player_power','role_reveal_boost_power','body_unreportable_power','special_vent_power','task_rollback_power','global_task_replace_power','trash_cleanup_death_power','muscle_task_pose_power','impostor_kill_win_power','sidekick_creation_power','madkiller_creation_power','revenant_creation_power','vent_disguise_move_power','fairy_chain_kill_power','kunai_projectile_power','launch_explosion_power','impostor_task_win_power','solo_impostor_unlock_power','promotion_power','live_task_win_power','missionary_power','forced_kill_misfire_power','obsession_power','shrine_power','mine_power','swallow_power','queen_servant_power','bet_target_win_power','skip_win_power','paint_area_win_power','chimera_creation_power','shadow_object_power','ironmate_power','trash_layer_power','curse_suicide_power','subteam_fallback_power','jackal_subteam_power','mad_teruteru_task_exile_win_power','guard_counter_vision_power','will_report_power','vote_visibility_power','revive_next_turn_power','impostor_judged_crewmate_power','yandere_subteam_power','queen_subteam_power','nonkill_fallback_power','liberal_fund_power','untargetable_power','combination_role_power','assassin_merlin_power','merlin_info_power','hero_villain_set_power','death_stage_power','crime_scene_power','assistant_report_power','apprentice_investigator_power','graffiti_power','wisp_light_power','same_group_awareness_power','support_target_power','role_guess_kill_power','object_move_power','speed_panel_power','skating_power','vote_swap_power','balance_vote_power','justice_balance_power','dying_message_power','sleep_bomb_power','tofu_fullness_power','chain_shift_power','scarlet_love_power','tyrant_kill_win_power','vanity_sheriff_power','opportunist_survival_power','balance_self_vote_mode_power','balance_self_target_option_power','balance_restrict_other_abilities_power','traitor_cracking_power','corpse_guard_charge_power','ambush_vent_kill_power','second_kill_button_power','puppeteer_kill_power','kill_quota_win_power','lights_only_kill_power','bounty_target_power','curse_target_power','kidnap_drag_power','curse_proxy_kill_power','bait_vent_detection_power','stock_reload_power','meeting_kill_power','last_impostor_boost_power','team_cooldown_boost_power','kill_combo_power','doll_creation_power','object_disguise_power','magic_circle_power','meeting_time_steal_power','mushroom_power','custom_sabotage_win_power','bombing_mode_power','hijack_vision_power','map_device_fake_power','time_stop_power','weapon_collect_power','punch_launch_power','vote_cancel_power','vision_debuff_power','task_meeting_time_power','task_public_reveal_power','killer_freeze_on_death_power','oil_douse_win_power','egoist_power','pavlov_owner_dog_power','schrodinger_cat_power','role_change_to_madmate_power','location_stay_win_power','three_pigs_team_power','monster_corpse_creation_power','corpse_nest_power','blackout_body_unlock_power','nekomata_revenge_power','suicide_wish_power','speed_boost_target_power','hawk_eye_power','door_manipulation_power','safecracker_power','matryoshka_power','god_power','evil_seer_power','black_hat_hack_power','false_accuse_power','push_drop_power','technician_power','stuntman_power','button_power','lighter_power','hamburger_task_power','data_hack_power','busker_power','crab_power','tracker_power','pumpkin_cat_power','moving_record_power','pteranodon_power','toilet_fan_power','clergyman_power','vulture_power','onmyoji_power','remote_control_power','medium_power'
]

def pb(v):
    v = (v or '').strip().lower()
    if v in {'true','yes','y','1','はい'}:
        return True
    if v in {'false','no','n','0','いいえ'}:
        return False
    return None

records = []
for r in rows:
    name = (r.get('name') or '').strip()
    display = (r.get('display_name') or name).strip()
    mod = (r.get('mod') or '').strip()
    feats = {}
    for k in feature_keys:
        v = pb(r.get(k))
        if v is not None:
            feats[k] = v
    records.append({'name': name, 'display': display, 'mod': mod, 'n': len(feats), 'feats': feats})

print('LOW_FEATURE_ROLES')
for rec in sorted(records, key=lambda x: (x['n'], x['name']))[:25]:
    print(f"{rec['n']:2d} | {rec['mod']:<8} | {rec['name']:<30} | {rec['display']}")

print('\nRARE_TRUE_FEATURES_LE_5')
true_counts = Counter()
for rec in records:
    for k, v in rec['feats'].items():
        if v:
            true_counts[k] += 1
for k, c in sorted(true_counts.items(), key=lambda x: (x[1], x[0])):
    if c <= 5:
        print(f"{c:2d}  {k}")
