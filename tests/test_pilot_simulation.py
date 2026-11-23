from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, get_db
from app.core.auth import AccountCredential, AdminAccess, get_current_user
from app.modules.users.models import User
from app.modules.users.datasets import DatasetAccount
from app.modules.study.models import StudyEnrollment
from app.modules.study.routes import summary_data
from app.modules.sessions.models import SessionRecord
from scripts.seed_pilot_simulation import seed


def test_simulation_is_repeatable_private_and_retrievable():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    @event.listens_for(engine,"connect")
    def enforce(conn,record):conn.execute("PRAGMA foreign_keys=ON")
    first=seed(engine)
    assert first==seed(engine)
    assert first["simulation_profiles"]==19 and first["tasks"]==152
    assert first["estimation"]["n"]==95
    assert first["human_participants"]==first["participant_reviews"]==first["llm_reviews"]==0
    with Session(engine,expire_on_commit=False) as db:
        assert db.scalar(select(func.count()).select_from(AccountCredential))==0
        fake=db.scalar(select(User).order_by(User.id))
        assert fake.consent_to_research=="false"
        assert db.scalar(select(DatasetAccount).where(DatasetAccount.user_id==fake.id)).source=="synthetic"
        # Even mistakenly granting research consent cannot make a fixture human evidence.
        fake.consent_to_research="true"
        db.add(StudyEnrollment(user_id=fake.id,baseline_frequency="often"))
        db.commit()
        assert summary_data(db)["consenting_participants"]==0
        operator=User(id="operator",email="operator@example.com",display_name="Operator")
        db.add(operator);db.flush();db.add(AdminAccess(user_id=operator.id));db.commit()
        app.dependency_overrides[get_db]=lambda:db
        client=TestClient(app)
        try:
            assert client.get("/api/v1/admin/simulation").status_code==401
            app.dependency_overrides[get_current_user]=lambda:fake
            assert client.get("/api/v1/admin/simulation").status_code==403
            assert client.get(f"/api/v1/insights?user_id={fake.id}&period=all").status_code==200
            session=db.scalar(select(SessionRecord).where(SessionRecord.user_id==fake.id))
            assert client.get(f"/api/v1/activity/sessions/{session.id}?user_id={fake.id}").status_code==200
            app.dependency_overrides[get_current_user]=lambda:operator
            result=client.get("/api/v1/admin/simulation")
            assert result.status_code==200,result.text
            assert result.json()["simulation_profiles"]==19
            assert result.json()["simulated_activity_intervals"]==4104
        finally:
            client.close();app.dependency_overrides.clear()
    engine.dispose()
