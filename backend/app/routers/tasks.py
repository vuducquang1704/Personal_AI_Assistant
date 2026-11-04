from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Priority, TaskStatus, User
from ..schemas import StatsOut, TaskIn, TaskOut, TaskUpdate
from ..security import get_current_user
from ..services import task_service as ts

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(status: TaskStatus | None = None, priority: Priority | None = None,
               due_from: datetime | None = None, due_to: datetime | None = None,
               q: str | None = None, overdue: bool = False, limit: int = Query(200, le=500),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ts.list_tasks(db, user, status=status.value if status else None,
                         priority=priority.value if priority else None, due_from=due_from, due_to=due_to,
                         search=q, overdue=overdue, limit=limit)


@router.post("", response_model=TaskOut, status_code=201)
def create(body: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ts.create_task(db, user, **body.model_dump())


@router.get("/stats", response_model=StatsOut)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ts.stats(db, user)


def _get(db, user, task_id):
    task = ts.get_task(db, user, task_id)
    if not task:
        raise HTTPException(404, "Không tìm thấy công việc")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get(db, user, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
def update(task_id: int, body: TaskUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ts.update_task(db, _get(db, user, task_id), **body.model_dump(exclude_unset=True))


@router.delete("/{task_id}", status_code=204)
def delete(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ts.delete_task(db, _get(db, user, task_id))
