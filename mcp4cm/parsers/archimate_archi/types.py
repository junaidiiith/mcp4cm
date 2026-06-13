"""
See ArchiMate Specification:
https://pubs.opengroup.org/architecture/archimate32-doc/ch-Summary-of-Language-Notation.html
"""

# Element types by layer
BUSINESS_TYPES = {
    "BusinessActor",
    "BusinessRole",
    "BusinessCollaboration",
    "BusinessInterface",
    "BusinessProcess",
    "BusinessFunction",
    "BusinessInteraction",
    "BusinessService",
    "BusinessEvent",
    "BusinessObject",
    "Contract",
    "Representation",
    "Product",
}

APPLICATION_TYPES = {
    "ApplicationComponent",
    "ApplicationCollaboration",
    "ApplicationInterface",
    "ApplicationProcess",
    "ApplicationFunction",
    "ApplicationInteraction",
    "ApplicationService",
    "ApplicationEvent",
    "DataObject",
}

TECHNOLOGY_TYPES = {
    "Node",
    "Device",
    "SystemSoftware",
    "TechnologyCollaboration",
    "TechnologyInterface",
    "TechnologyProcess",
    "TechnologyFunction",
    "TechnologyInteraction",
    "TechnologyService",
    "TechnologyEvent",
    "Artifact",
    "CommunicationNetwork",
    "Path",
}

PHYSICAL_TYPES = {"Equipment", "DistributionNetwork", "Facility", "Material"}

MOTIVATION_TYPES = {
    "Stakeholder",
    "Driver",
    "Assessment",
    "Goal",
    "Outcome",
    "Principle",
    "Requirement",
    "Constraint",
    "Value",
    "Meaning",
}

STRATEGY_TYPES = {"Resource", "Capability", "ValueStream", "CourseOfAction"}

IMPLEMENTATION_MIGRATION_TYPES = {"WorkPackage", "ImplementationEvent", "Deliverable", "Plateau", "Gap"}

OTHER_TYPES = {"Location", "Grouping", "Junction", "OrJunction", "AndJunction"}

RELATIONSHIP_TYPES = {
    "Association",
    "Serving",
    "Flow",
    "Realization",
    "Aggregation",
    "Influence",
    "Composition",
    "Triggering",
    "Assignment",
    "Specialization",
    "Access",
}

# All valid element types (nodes)
ALL_ELEMENT_TYPES = (
    BUSINESS_TYPES
    | APPLICATION_TYPES
    | TECHNOLOGY_TYPES
    | PHYSICAL_TYPES
    | MOTIVATION_TYPES
    | STRATEGY_TYPES
    | IMPLEMENTATION_MIGRATION_TYPES
    | OTHER_TYPES
)

# All valid relationship types (edges)
ALL_RELATIONSHIP_TYPES = RELATIONSHIP_TYPES

# All valid types (both elements and relationships)
ALL_TYPES = ALL_ELEMENT_TYPES | ALL_RELATIONSHIP_TYPES

# Type renaming map for deprecated types
# Maps deprecated type names to their current equivalents
# Note: For relationships ending in "Relationship", the normalization step will
# remove the "Relationship" suffix after renaming
TYPE_RENAMES = {
    "InfrastructureInterface": "TechnologyInterface",
    "InfrastructureFunction": "TechnologyFunction",
    "InfrastructureService": "TechnologyService",
    "CommunicationPath": "Path",
    "Network": "CommunicationNetwork",
    "Realisation": "Realization",
    "Specialisation": "Specialization",
    "UsedBy": "Serving",
}
