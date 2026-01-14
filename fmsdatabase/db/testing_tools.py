from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class TestingTools(Base):
    __tablename__ = 'testing_tools'
    id = Column(Integer, primary_key = True, autoincrement = True, nullable = False)
    description = Column(String(100), nullable = False)
    serial_number = Column(String(255), unique = True, nullable = False)
    model = Column(String(255), nullable = False)
    equipment_range = Column(String(255), nullable = False)
    accuracy = Column(String(255), nullable = False)
    next_calibration_date = Column(DateTime, nullable = False)
    last_calibration_date = Column(DateTime, nullable = False)