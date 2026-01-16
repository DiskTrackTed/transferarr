"""
Marshmallow validation schemas for API request validation.

These schemas are used by the @validate_json decorator to validate
incoming request data before it reaches the route handlers.
"""
from marshmallow import Schema, fields, validate, validates_schema, ValidationError


# =============================================================================
# Download Client Schemas
# =============================================================================

class DownloadClientSchema(Schema):
    """Schema for POST /api/v1/download_clients"""
    name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(required=True)  # Required for new clients
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))


class DownloadClientUpdateSchema(Schema):
    """Schema for PUT /api/v1/download_clients/<name>
    
    Similar to DownloadClientSchema but:
    - name is not included (comes from URL path)
    - password is optional (uses stored password if not provided)
    """
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(load_default=None)  # Optional - uses stored if not provided
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))


class DownloadClientTestSchema(Schema):
    """Schema for POST /api/v1/download_clients/test
    
    Similar to DownloadClientSchema but:
    - name is optional (only provided when editing existing client for stored password lookup)
    - password is optional (uses stored password when editing)
    """
    name = fields.Str(load_default=None)  # Optional - for stored password lookup when editing
    type = fields.Str(required=True, validate=validate.OneOf(["deluge"]))
    host = fields.Str(required=True, validate=validate.Length(min=1))
    port = fields.Int(required=True, validate=validate.Range(min=1, max=65535))
    username = fields.Str(allow_none=True, load_default=None)
    password = fields.Str(load_default=None)  # Optional - uses stored if editing existing client
    connection_type = fields.Str(required=True, validate=validate.OneOf(["rpc", "web"]))


# =============================================================================
# Connection Schemas
# =============================================================================

class SFTPConfigSchema(Schema):
    """Schema for SFTP connection configuration.
    
    Either (host, port, username, password) OR (ssh_config_file, ssh_config_host) should be provided.
    """
    # Direct connection options
    host = fields.Str(load_default=None)
    port = fields.Int(validate=validate.Range(min=1, max=65535), load_default=22)
    username = fields.Str(load_default=None)
    password = fields.Str(load_default=None)
    private_key = fields.Str(load_default=None)
    
    # SSH config file options
    ssh_config_file = fields.Str(load_default=None)
    ssh_config_host = fields.Str(load_default=None)


class TransferConfigSideSchema(Schema):
    """Schema for one side (from/to) of a transfer configuration."""
    type = fields.Str(required=True, validate=validate.OneOf(["local", "sftp"]))
    sftp = fields.Nested(SFTPConfigSchema, load_default=None)


class TransferConfigSchema(Schema):
    """Schema for the transfer_config object."""
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Nested(TransferConfigSideSchema, required=True, data_key="from")
    to = fields.Nested(TransferConfigSideSchema, required=True)


class ConnectionSchema(Schema):
    """Schema for POST /api/v1/connections
    
    Phase 4: name is required and used as unique identifier.
    """
    name = fields.Str(
        required=True, 
        validate=[
            validate.Length(min=1),
            validate.Regexp(r'^[^/]+$', error="Connection name cannot contain '/'")
        ]
    )
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Nested(TransferConfigSchema, required=True)
    source_dot_torrent_path = fields.Str(required=True)
    source_torrent_download_path = fields.Str(required=True)
    destination_dot_torrent_tmp_dir = fields.Str(required=True)
    destination_torrent_download_path = fields.Str(required=True)


class ConnectionUpdateSchema(Schema):
    """Schema for PUT /api/v1/connections/<name>
    
    Similar to ConnectionSchema but:
    - name is optional (only provided for renaming)
    - Connection identified by URL path parameter
    """
    name = fields.Str(
        load_default=None,
        validate=[
            validate.Length(min=1),
            validate.Regexp(r'^[^/]+$', error="Connection name cannot contain '/'")
        ]
    )
    # Use data_key to map Python's 'from_' to JSON's 'from'
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Nested(TransferConfigSchema, required=True)
    source_dot_torrent_path = fields.Str(required=True)
    source_torrent_download_path = fields.Str(required=True)
    destination_dot_torrent_tmp_dir = fields.Str(required=True)
    destination_torrent_download_path = fields.Str(required=True)


class ConnectionTestSchema(Schema):
    """Schema for POST /api/v1/connections/test
    
    Phase 4.5: connection_name is optional for stored password lookup when editing.
    """
    connection_name = fields.Str(load_default=None)  # Optional - for stored password lookup
    from_ = fields.Str(required=True, data_key="from")
    to = fields.Str(required=True)
    transfer_config = fields.Nested(TransferConfigSchema, required=True)


# =============================================================================
# Utility Schemas
# =============================================================================

class BrowseRequestSchema(Schema):
    """Schema for POST /api/v1/browse"""
    type = fields.Str(required=True, validate=validate.OneOf(["local", "sftp"]))
    path = fields.Str(load_default="/")
    sftp = fields.Nested(SFTPConfigSchema, load_default=None)
