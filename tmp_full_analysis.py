from verify_role_guesser_accuracy_tmp import load_namespace
from difflib import SequenceMatcher
from collections import defaultdict
import csv, os
namespace = load_namespace()
roles = namespace['load_roles']()
out_dir = 'analysis'
os.makedirs(out_dir, exist_ok=True)
# duplicates by display_name
disp_map=defaultdict(list)
for r in roles:
    disp_map[r.display_name.strip()].append((r.name,r.mod))
with open(os.path.join(out_dir,'duplicate_display.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['display_name','count','entries'])
    for k,v in sorted(disp_map.items(), key=lambda x:-len(x[1])):
        if len(v)>1:
            writer.writerow([k,len(v),';'.join([f'{n}@{m}' for n,m in v])])
# similar name pairs
pairs=[]
names=[(r.name,r.display_name,r.mod) for r in roles]
for i,(n1,d1,m1) in enumerate(names):
    for j,(n2,d2,m2) in enumerate(names[i+1:],start=i+1):
        if not n1 or not n2: continue
        if n1==n2: continue
        r=SequenceMatcher(None,n1.lower(),n2.lower()).ratio()
        if r>=0.85:
            pairs.append((r,n1,d1,m1,n2,d2,m2))
with open(os.path.join(out_dir,'similar_name_pairs.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['ratio','name1','display1','mod1','name2','display2','mod2'])
    for p in sorted(pairs,reverse=True): writer.writerow(p)
# similar display pairs
pairs2=[]
for i,(n1,d1,m1) in enumerate(names):
    for j,(n2,d2,m2) in enumerate(names[i+1:],start=i+1):
        if not d1 or not d2: continue
        if d1==d2: continue
        r=SequenceMatcher(None,d1.lower(),d2.lower()).ratio()
        if r>=0.90:
            pairs2.append((r,n1,d1,m1,n2,d2,m2))
with open(os.path.join(out_dir,'similar_display_pairs.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['ratio','name1','display1','mod1','name2','display2','mod2'])
    for p in sorted(pairs2,reverse=True): writer.writerow(p)
# run full resolution for all roles
role_map={r.name:r for r in roles}
results=[]
for r in roles:
    pool=[candidate for candidate in roles if candidate.mod==r.mod]
    session=namespace['GuessSession'](0,pool,r.mod)
    max_steps=60
    for _ in range(max_steps):
        namespace['expand_final_candidates_if_needed'](session)
        final_allowed= not namespace['should_delay_final_result'](session)
        if final_allowed and namespace['single_group_roles'](session.candidates):
            finished,exact_result=True,True
            break
        if final_allowed and len(session.candidates)==1:
            finished,exact_result=True,True
            break
        if namespace['best_question'](session.candidates, session.asked) is None:
            finished,exact_result=True,False
            break
        q=session.next_question()
        if not q:
            finished,exact_result=True,False
            break
        ans = (q.startswith('guess:') and q.removeprefix('guess:')==r.name) or (r.features.get(q) is True)
        session.apply_answer(ans)
        session.current_question=None
    final_candidates=[c.name for c in session.candidates]
    hit = r.name in final_candidates
    results.append((r.mod,r.name,r.display_name,session.answered_question_count,session.positive_answer_count,len(final_candidates),hit,finished,exact_result,'|'.join(final_candidates)))
with open(os.path.join(out_dir,'role_results.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['mod','name','display_name','answered_qs','positive_qs','final_candidate_count','hit','finished','exact_result','final_candidates'])
    for row in results: writer.writerow(row)
# ambiguous roles
amb=[r for r in results if r[5]>1]
with open(os.path.join(out_dir,'ambiguous_roles.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['mod','name','display_name','answered_qs','positive_qs','final_candidate_count','final_candidates'])
    for r in sorted(amb,key=lambda x:-x[5]): writer.writerow((r[0],r[1],r[2],r[3],r[4],r[5],r[9]))
# suggestions
sugg=[]
for r in amb:
    sugg.append(f"Role {r[1]}@{r[0]} ambiguous with {r[9]} -> consider adding features distinguishing: team, can_kill, uses_vent, meeting_ability")
with open(os.path.join(out_dir,'suggestions.txt'),'w',encoding='utf-8') as f:
    if sugg:
        f.write('\n'.join(sugg))
    else:
        f.write('No ambiguous roles found.')
# summary
print('WROTE',out_dir)
print('total_roles',len(roles))
print('duplicate_display_groups',sum(1 for k,v in disp_map.items() if len(v)>1))
print('similar_name_pairs',len(pairs))
print('similar_display_pairs',len(pairs2))
print('ambiguous_roles',len(amb))
print('files: duplicate_display.csv, similar_name_pairs.csv, similar_display_pairs.csv, role_results.csv, ambiguous_roles.csv, suggestions.txt')
print('\nDone')
