from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Float, Enum
from ..utils.enums import FMSProgressStatus
from sqlalchemy.orm import relationship
from .base import Base

class FMSMain(Base):
    """
    ------------------
    FMS Main table 1.0
    ------------------

    Columns
    -------
    fms_id : String(50)
        Primary Key. FMS Identifier.
    project : Integer
        Project number associated with the FMS.
    id : Integer
        Auto-incrementing identifier.
    drawing : String(50)
        Drawing number associated with the FMS.
    gas_type : String(50)
        Gas type that the FMS is designed and tested for.
    hpiv_id : String(50)
        Identifier for the HPIV component.
    tv_id : String(50)
        Identifier for the Thermal Valve component.
    manifold_id : String(50)
        Identifier for the Manifold component.
    lpt_id : String(50)
        Identifier for the LPT component.
    anode_fr_id : String(50)
        Identifier for the Anode FR component.
    cathode_fr_id : String(50)
        Identifier for the Cathode FR component.
    model : String(50)
        Model number of the FMS.
    status : Enum(FMSProgressStatus)
        Current progress status of the FMS.
    rfs : String(50)
        Ready for Shipment identifier.
    test_doc_ref : String(100)
        Reference to the test documentation.

    Relationships
    -------------
    limits : FMSLimits
        One-to-one relationship with FMSLimits table.
    fr_tests : FMSFRTests
        One-to-many relationship with FMSFRTests table.
    test_results : FMSTestResults
        One-to-many relationship with FMSTestResults table.
    functional_tests : FMSFunctionalTests
        One-to-many relationship with FMSFunctionalTests table.
    tvac_results : FMSTvac
        One-to-many relationship with FMSTvac table.
    hpiv : HPIVCertification
        One-to-one relationship with HPIVCertification table.
    thermal_valve : TVStatus
        One-to-one relationship with TVStatus table.
    manifold : ManifoldStatus
        One-to-one relationship with ManifoldStatus table.
    acceptance_tests : FMSAcceptanceTests
        One-to-one relationship with FMSAcceptanceTests table.
    """
    __tablename__ = 'fms_main'
    fms_id = Column(String(50), primary_key=True, nullable=False)
    project = Column(Integer, nullable=True)
    id = Column(Integer, autoincrement=True, nullable=False)
    drawing = Column(String(50), nullable=True)
    gas_type = Column(String(50), nullable=True)
    hpiv_id = Column(String(50), nullable=True)
    tv_id = Column(String(50), nullable=True)
    manifold_id = Column(String(50), nullable=True)
    lpt_id = Column(String(50), nullable=True)
    anode_fr_id = Column(String(50), nullable=True)
    cathode_fr_id = Column(String(50), nullable=True)
    model = Column(String(50), nullable=True)
    status = Column(Enum(FMSProgressStatus, native_enum=False), nullable=True)
    rfs = Column(String(50), nullable=True)
    test_doc_ref = Column(String(100), nullable=True)

    limits = relationship("FMSLimits", back_populates="fms_main", uselist=False)
    fr_tests = relationship("FMSFRTests", back_populates="fms_main")
    test_results = relationship("FMSTestResults", back_populates="fms_main")
    functional_tests = relationship("FMSFunctionalTests", back_populates="fms_main")
    tvac_results = relationship("FMSTvac", back_populates="fms_main")
    hpiv = relationship("HPIVCertification", back_populates="fms_main")
    thermal_valve = relationship("TVStatus", back_populates="fms_main")
    manifold = relationship("ManifoldStatus", back_populates="fms_main")
    acceptance_tests = relationship("FMSAcceptanceTests", back_populates="fms_main")