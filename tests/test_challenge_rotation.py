from challenge_rotation import authoritative_solved, choose_next, eligible

def _challenge(cid, reward, status="OPEN + FUNDED", solved=False):
    return {"id":cid,"title":cid,"status":status,"balance_btc":reward,
            "provenance":{"url":"https://example.org/challenge/"+cid},
            "verification":{"method":"published verifier"},
            "external_status":({"status":"SOLVED","verified":True,
              "evidence_url":"https://example.org/tx/abc","evidence_id":"abc"} if solved else {})}

def test_external_solution_requires_authoritative_evidence():
    assert authoritative_solved(_challenge("a",1,solved=True))
    row=_challenge("b",1,solved=True); row["external_status"]["verified"]=False
    assert not authoritative_solved(row)

def test_rotation_marks_external_solution_and_selects_next():
    current=_challenge("current",.5,solved=True); next_one=_challenge("next",.2)
    decision=choose_next([current,next_one],"current")
    assert decision.active_id=="next"; assert decision.retired_id=="current"
    assert current["status"]=="EXTERNAL_SOLVED"

def test_rotation_keeps_current_if_still_open_and_funded():
    current=_challenge("current",.5)
    assert choose_next([current],"current").active_id=="current"

def test_unfunded_and_solved_records_are_not_candidates():
    assert not eligible(_challenge("empty",0,"OPEN + UNFUNDED"))
    assert not eligible(_challenge("solved",1,"SOLVED"))
