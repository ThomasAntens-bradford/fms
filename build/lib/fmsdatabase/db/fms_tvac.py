from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum, DateTime
from ..utils.general_utils import LimitStatus
from sqlalchemy.orm import relationship
from .base import Base

class FMSTvac(Base):
    """
    --------------------------
    FMS TVAC Results table 1.4
    --------------------------

    Columns
    -------
    id : Integer
        Primary Key. Auto-incrementing identifier.
    fms_id : String(50)
        Foreign Key. FMS Identifier linking to FMSMain table.
    test_id : String(50)
        Identifier for the TVAC test.
    date : DateTime
        Date and time when the test was conducted.
    logtime : JSON
        List of timestamps at which the measurements were logged, in ISO 8601 format.
    trp1 : JSON
        List of TRP1 temperatures recorded during the test.
    trp2 : JSON
        List of TRP2 temperatures recorded during the test.
    hpiv : JSON
        List of HPIV temperatures recorded during the test.
    manifold : JSON
        List of Manifold temperatures recorded during the test.
    lpt : JSON
        List of LPT temperatures recorded during the test.
    tv_inlet : JSON
        List of Thermal Valve inlet temperatures recorded during the test.
    tv_outlet : JSON
        List of Thermal Valve outlet temperatures recorded during the test.
    fms_inlet : JSON
        List of FMS inlet temperatures recorded during the test.
    anode : JSON
        List of Anode temperatures recorded during the test.
    cathode : JSON
        List of Cathode temperatures recorded during the test.
    remark : String(255)
        Additional remarks or comments about the test.

    Relationships
    -------------
    fms_main : FMSMain
        Many-to-one relationship with FMSMain table.
    """
    __tablename__ = 'fms_tvac'
    id = Column(Integer, primary_key=True, autoincrement=True)
    fms_id = Column(String(50), ForeignKey('fms_main.fms_id'), nullable=False)
    test_id = Column(String(50), nullable=False)
    date = Column(DateTime, nullable=True)
    logtime = Column(JSON, nullable=False)
    trp1 = Column(JSON, nullable=True)
    trp2 = Column(JSON, nullable=True)
    hpiv = Column(JSON, nullable=True)
    manifold = Column(JSON, nullable=True)
    lpt = Column(JSON, nullable=True)
    tv_inlet = Column(JSON, nullable=True)
    tv_outlet = Column(JSON, nullable=True)
    fms_inlet = Column(JSON, nullable=True)
    anode = Column(JSON, nullable=True)
    cathode = Column(JSON, nullable=True)
    remark = Column(String(255), nullable=True)

    fms_main = relationship("FMSMain", back_populates="tvac_results")
