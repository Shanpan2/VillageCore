from verify_role_guesser_accuracy_tmp import load_namespace
from difflib import SequenceMatcher
from collections import defaultdict
import csv, os, time

start=time.time()
namespace = load_namespace()
roles = namespace['load_roles']()
print('loaded roles',len(roles))
out_dir = 'analysis'
os.makedirs(out_dir, exist_ok=True)

# duplicate display names
disp_map=defaultdict(list)
for r in roles:
    disp_map[r.display_name.strip()].append((r.name,r.mod))
with open(os.path.join(out_dir,'duplicate_display.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['display_name','count','entries'])
    for k,v in disp_map.items():
        if len(v)>1:
            writer.writerow([k,len(v),';'.join([f'{n}@{m}' for n,m in v])])
print('wrote duplicate_display.csv')

# similar internal names (>=0.85)
names=[(r.name,r.display_name,r.mod) for r in roles]
with open(os.path.join(out_dir,'similar_name_pairs.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['ratio','name1','display1','mod1','name2','display2','mod2'])
    for i,(n1,d1,m1) in enumerate(names):
        for n2,d2,m2 in names[i+1:]:
            if not n1 or not n2: continue
            if n1==n2: continue
            r=SequenceMatcher(None,n1.lower(),n2.lower()).ratio()
            if r>=0.85:
                writer.writerow((f"{r:.3f}",n1,d1,m1,n2,d2,m2))
print('wrote similar_name_pairs.csv')

# similar display names (>=0.90)
with open(os.path.join(out_dir,'similar_display_pairs.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['ratio','name1','display1','mod1','name2','display2','mod2'])
    for i,(n1,d1,m1) in enumerate(names):
        for n2,d2,m2 in names[i+1:]:
            if not d1 or not d2: continue
            if d1==d2: continue
            r=SequenceMatcher(None,d1.lower(),d2.lower()).ratio()
            if r>=0.90:
                writer.writerow((f"{r:.3f}",n1,d1,m1,n2,d2,m2))
print('wrote similar_display_pairs.csv')

# run resolution for all roles, but stop early when candidates <=2 to save time
results=[]
count=0
for r in roles:
    count+=1
    if count%100==0:
        print('processing',count,'/',len(roles))
    pool=[c for c in roles if c.mod==r.mod]
    session=namespace['GuessSession'](0,pool,r.mod)
    max_steps=60
    for _ in range(max_steps):
        q=session.next_question()
        if not q:
            break
        ans = (q.startswith('guess:') and q.removeprefix('guess:')==r.name) or (r.features.get(q) is True)
        session.apply_answer(ans)
        session.current_question=None
        if len(session.candidates)<=2:
            break
    final_candidates=[c.name for c in session.candidates]
    hit = r.name in final_candidates
    results.append((r.mod,r.name,r.display_name,session.answered_question_count,session.positive_answer_count,len(final_candidates),hit,'|'.join(final_candidates)))

with open(os.path.join(out_dir,'role_results.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['mod','name','display_name','answered_qs','positive_qs','final_candidate_count','hit','final_candidates'])
    for row in results: writer.writerow(row)
print('wrote role_results.csv')

amb=[r for r in results if r[5]>1]
with open(os.path.join(out_dir,'ambiguous_roles.csv'),'w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['mod','name','display_name','answered_qs','positive_qs','final_candidate_count','final_candidates'])
    for r in sorted(amb,key=lambda x:-x[5]): writer.writerow((r[0],r[1],r[2],r[3],r[4],r[5],r[7]))
print('wrote ambiguous_roles.csv',len(amb))

# simple suggestions
with open(os.path.join(out_dir,'suggestions.txt'),'w',encoding='utf-8') as f:
    if amb:
        for r in amb:
            f.write(f"Role {r[1]}@{r[0]} ambiguous with {r[7]} -> consider adding distinguishing features (team, can_kill, uses_vent, meeting_ability)\n")
    else:
        f.write('No ambiguous roles found.')
print('wrote suggestions.txt')
print('elapsed',time.time()-start)
print('done')
