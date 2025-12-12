from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from .base import Base

class TVTvac(Base):
    """
    -------------------
    TV TVAC table 1.6.3
    -------------------

    Columns
    -------
    test_id : String(50)
        Primary Key. TVAC Test Identifier.
    tv_id : Integer
        Foreign Key. TV Identifier linking to TVStatus table.
    time : JSON
        List of time measurements during the TVAC test.
    outlet_temp_1 : JSON
        List of outlet temperature 1 measurements during the TVAC test.
    outlet_temp_2 : JSON
        List of outlet temperature 2 measurements during the TVAC test.
    interface_temp : JSON
        List of interface temperature measurements during the TVAC test.
    if_plate : JSON
        List of IF plate temperature measurements during the TVAC test.
    tv_voltage : JSON
        List of TV voltage measurements during the TVAC test.
    tv_current : JSON
        List of TV current measurements during the TVAC test.
    vacuum : JSON
        List of vacuum measurements during the TVAC test.
    cycles : Integer
        Number of cycles completed during the TVAC test.

    Relationships
    -------------
    status : TVStatus
        Many-to-one relationship with TVStatus table.
    """
    __tablename__ = 'tv_tvac'

    test_id = Column(String(50), primary_key=True, nullable=False)
    tv_id = Column(Integer, ForeignKey('tv_status.tv_id'), nullable=False)
    time = Column(JSON, nullable=False)
    outlet_temp_1 = Column(JSON, nullable=False)
    outlet_temp_2 = Column(JSON, nullable=False)
    interface_temp = Column(JSON, nullable=False)
    if_plate = Column(JSON, nullable=False)
    tv_voltage = Column(JSON, nullable=False)
    tv_current = Column(JSON, nullable=False)  
    vacuum = Column(JSON, nullable=False)
    cycles = Column(Integer, nullable=False)

    status = relationship("TVStatus", back_populates="tvac")
