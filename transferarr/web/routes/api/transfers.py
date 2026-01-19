"""
Transfer history routes for listing and viewing transfer records.
"""
from flask import current_app, request
from .responses import success_response, error_response, not_found_response, server_error_response
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register transfer history routes with the given blueprint."""
    
    @bp.route("/transfers")
    def list_transfers():
        """Get transfer history with filtering and pagination.
        ---
        tags:
          - Transfers
        parameters:
          - in: query
            name: page
            type: integer
            default: 1
            description: Page number (1-indexed)
          - in: query
            name: per_page
            type: integer
            default: 25
            description: Items per page (max 100)
          - in: query
            name: status
            type: string
            enum: [pending, transferring, completed, failed, cancelled]
            description: Filter by transfer status
          - in: query
            name: source
            type: string
            description: Filter by source client name
          - in: query
            name: target
            type: string
            description: Filter by target client name
          - in: query
            name: search
            type: string
            description: Search in torrent name
          - in: query
            name: from_date
            type: string
            format: date
            description: Filter by created_at >= date (ISO format)
          - in: query
            name: to_date
            type: string
            format: date
            description: Filter by created_at <= date (ISO format)
          - in: query
            name: sort
            type: string
            enum: [created_at, completed_at, size_bytes, torrent_name]
            default: created_at
            description: Sort field
          - in: query
            name: order
            type: string
            enum: [asc, desc]
            default: desc
            description: Sort order
        responses:
          200:
            description: Paginated list of transfers
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    transfers:
                      type: array
                      items:
                        $ref: '#/definitions/Transfer'
                    total:
                      type: integer
                      description: Total number of matching transfers
                    page:
                      type: integer
                    per_page:
                      type: integer
                    pages:
                      type: integer
                      description: Total number of pages
          400:
            description: Invalid status parameter
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            # Parse query parameters
            page = request.args.get('page', 1, type=int)
            per_page = min(request.args.get('per_page', 25, type=int), 100)
            status = request.args.get('status')
            source = request.args.get('source')
            target = request.args.get('target')
            search = request.args.get('search')
            from_date = request.args.get('from_date')
            to_date = request.args.get('to_date')
            sort = request.args.get('sort', 'created_at')
            order = request.args.get('order', 'desc')
            
            # Validate status if provided
            valid_statuses = ('pending', 'transferring', 'completed', 'failed', 'cancelled')
            if status and status not in valid_statuses:
                return error_response(
                    "VALIDATION_ERROR",
                    f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}",
                    status_code=400
                )
            
            transfers, total = history_service.list_transfers(
                status=status,
                source=source,
                target=target,
                search=search,
                start_date=from_date,
                end_date=to_date,
                page=page,
                per_page=per_page,
                sort=sort,
                order=order
            )
            
            # Calculate total pages
            pages = (total + per_page - 1) // per_page if per_page > 0 else 0
            
            return success_response({
                "transfers": transfers,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": pages
            })
        except Exception as e:
            logger.error(f"Error listing transfers: {e}")
            return server_error_response(str(e))
    
    @bp.route("/transfers/active")
    def get_active_transfers():
        """Get all currently active (pending/transferring) transfers.
        ---
        tags:
          - Transfers
        responses:
          200:
            description: List of active transfers
            schema:
              type: object
              properties:
                data:
                  type: array
                  items:
                    $ref: '#/definitions/Transfer'
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            transfers = history_service.get_active_transfers()
            return success_response(transfers)
        except Exception as e:
            logger.error(f"Error getting active transfers: {e}")
            return server_error_response(str(e))
    
    @bp.route("/transfers/stats")
    def get_transfer_stats():
        """Get aggregate transfer statistics.
        ---
        tags:
          - Transfers
        responses:
          200:
            description: Transfer statistics
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    total:
                      type: integer
                      description: Total number of transfers
                    completed:
                      type: integer
                      description: Number of completed transfers
                    failed:
                      type: integer
                      description: Number of failed transfers
                    pending:
                      type: integer
                      description: Number of pending transfers
                    transferring:
                      type: integer
                      description: Number of in-progress transfers
                    success_rate:
                      type: number
                      description: Percentage of successful transfers (0-100)
                    total_bytes_transferred:
                      type: integer
                      description: Total bytes transferred across all completed transfers
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            stats = history_service.get_stats()
            return success_response(stats)
        except Exception as e:
            logger.error(f"Error getting transfer stats: {e}")
            return server_error_response(str(e))
    
    @bp.route("/transfers/<transfer_id>")
    def get_transfer(transfer_id):
        """Get a single transfer by ID.
        ---
        tags:
          - Transfers
        parameters:
          - in: path
            name: transfer_id
            type: string
            required: true
            description: Transfer UUID
        responses:
          200:
            description: Transfer details
            schema:
              type: object
              properties:
                data:
                  $ref: '#/definitions/Transfer'
          404:
            description: Transfer not found
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            transfer = history_service.get_transfer(transfer_id)
            if not transfer:
                return not_found_response("Transfer", transfer_id)
            
            return success_response(transfer)
        except Exception as e:
            logger.error(f"Error getting transfer {transfer_id}: {e}")
            return server_error_response(str(e))
    
    @bp.route("/transfers/<transfer_id>", methods=["DELETE"])
    def delete_transfer(transfer_id):
        """Delete a single transfer record.
        ---
        tags:
          - Transfers
        parameters:
          - in: path
            name: transfer_id
            type: string
            required: true
            description: Transfer UUID to delete
          - in: query
            name: force
            type: boolean
            default: false
            description: Force delete even if transfer is active (for stuck transfers)
        responses:
          200:
            description: Transfer deleted successfully
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    deleted:
                      type: boolean
                message:
                  type: string
          400:
            description: Cannot delete active transfer (use force=true to override)
          404:
            description: Transfer not found
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            # Check if transfer exists
            transfer = history_service.get_transfer(transfer_id)
            if not transfer:
                return not_found_response("Transfer", transfer_id)
            
            # Block deletion of active transfers unless force=true
            force = request.args.get('force', 'false').lower() == 'true'
            if not force and transfer['status'] in ('pending', 'transferring'):
                return error_response(
                    "VALIDATION_ERROR",
                    "Cannot delete active transfer. Wait for it to complete, or use force=true to delete stuck transfers.",
                    status_code=400
                )
            
            deleted = history_service.delete_transfer(transfer_id)
            # We already checked existence above, so this should always succeed
            
            return success_response({"deleted": True}, f"Transfer {transfer_id} deleted")
        except Exception as e:
            logger.error(f"Error deleting transfer {transfer_id}: {e}")
            return server_error_response(str(e))
    
    @bp.route("/transfers", methods=["DELETE"])
    def clear_transfers():
        """Clear transfer history records.
        ---
        tags:
          - Transfers
        parameters:
          - in: query
            name: status
            type: string
            enum: [completed, failed, cancelled]
            description: Only delete records with this status. If omitted, deletes all completed/failed/cancelled.
        responses:
          200:
            description: History cleared successfully
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    deleted_count:
                      type: integer
                message:
                  type: string
          400:
            description: Invalid status parameter
          503:
            description: Transfer history service not available
          500:
            description: Server error
        """
        try:
            history_service = _get_history_service()
            if not history_service:
                return error_response(
                    "SERVICE_UNAVAILABLE",
                    "Transfer history service not available",
                    status_code=503
                )
            
            status = request.args.get('status')
            
            # Validate status if provided
            if status and status not in ('completed', 'failed', 'cancelled'):
                return error_response(
                    "VALIDATION_ERROR",
                    f"Invalid status '{status}'. Must be one of: completed, failed, cancelled",
                    status_code=400
                )
            
            deleted_count = history_service.clear_history(status)
            
            status_msg = f" with status '{status}'" if status else ""
            return success_response(
                {"deleted_count": deleted_count}, 
                f"Deleted {deleted_count} transfer record(s){status_msg}"
            )
        except Exception as e:
            logger.error(f"Error clearing transfers: {e}")
            return server_error_response(str(e))


def _get_history_service():
    """Get the history service from the torrent manager."""
    torrent_manager = current_app.config.get('TORRENT_MANAGER')
    if torrent_manager:
        return getattr(torrent_manager, 'history_service', None)
    return None
