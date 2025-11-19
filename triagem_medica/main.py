from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models, schemas
from services import create_patient, authenticate_patient, run_triage, recommend_medications
from auth import create_access_token, decode_token

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Triagem Médica - Backend (API)")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_username(token: str = Depends(oauth2_scheme)):
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    return username

# Auth
@app.post("/auth/register", response_model=schemas.PatientOut)
def register(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Patient).filter(models.Patient.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já existe")
    user = create_patient(db, payload.username, payload.password, payload.full_name or "", payload.allergies or "")
    return user

@app.post("/auth/token", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_patient(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")
    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer"}

# Patient endpoints
@app.get("/patients/me", response_model=schemas.PatientOut)
def read_me(username: str = Depends(get_current_username), db: Session = Depends(get_db)):
    user = db.query(models.Patient).filter(models.Patient.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user

# CRUD Medications (minimal)
@app.post("/medications", response_model=schemas.MedicationOut)
def add_med(med: schemas.MedicationCreate, username: str = Depends(get_current_username), db: Session = Depends(get_db)):
    m = models.Medication(name=med.name, indications=med.indications or "", contraindications=med.contraindications or "", allergy_tags=med.allergy_tags or "", notes=med.notes or "")
    db.add(m); db.commit(); db.refresh(m)
    return m

@app.get("/medications", response_model=list[schemas.MedicationOut])
def list_meds(db: Session = Depends(get_db)):
    return db.query(models.Medication).all()

# Triage
@app.post("/triage", response_model=schemas.TriageOut)
def create_triage(payload: schemas.TriageRequest, username: str = Depends(get_current_username), db: Session = Depends(get_db)):
    user = db.query(models.Patient).filter(models.Patient.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    tr = run_triage(db, user.id, payload.symptoms)
    return tr

@app.get("/triage/{triage_id}/recommendations", response_model=list[schemas.RecommendationOut])
def get_recommendations(triage_id: int, username: str = Depends(get_current_username), db: Session = Depends(get_db)):
    tr = db.query(models.Triage).filter(models.Triage.id == triage_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Triagem não encontrada")
    if tr.patient and tr.patient.username != username:
        # permitir apenas dono (simples)
        raise HTTPException(status_code=403, detail="Acesso negado")
    recs = recommend_medications(db, tr)
    return recs
