# -*- coding: utf-8 -*-
from __future__ import absolute_import

import django_filters
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .base import WsListAPIView, WsRetrieveAPIView
from .exception import OperationNotAllowed, OperationFailed
import rest.models
import rest.serializers
import rest.filters
from tasknode.tasks import handle_placed_order, send_emails_for_placed_order


class OrderQuerysetMixin(object):
    """
    This is a mixin class that provides queryset retrieval based on the privileges of the
    requesting user.
    """

    def _get_user_queryset(self):
        return self.request.user.orders.all()

    def _get_su_queryset(self):
        return rest.models.Order.objects.all()


class OrderListView(OrderQuerysetMixin, WsListAPIView):
    """
    Get all orders.
    """

    serializer_class = rest.serializers.OrderSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filter_class = rest.filters.OrderFilter


class OrderDetailView(OrderQuerysetMixin, WsRetrieveAPIView):
    """
    get:
    Get a specific order.
    """

    serializer_class = rest.serializers.OrderSerializer


@api_view(["PUT"])
def place_order(request, pk=None):
    """
    Place a specific order.
    """
    order = get_object_or_404(rest.models.Order, pk=pk)
    if not request.user.is_superuser:
        if not order.organization.can_user_scan(request.user):
            raise PermissionDenied("You do not have sufficient privileges to start scans for that organization.")
    elif order.has_been_placed:
        raise PermissionDenied("That order has already been placed.")
    order_placed = order.place_order()
    if not order_placed:
        raise OperationFailed("An issue was encountered when attempting to place your order. Please try again.")
    order.save()
    send_emails_for_placed_order.delay(
        order_uuid=unicode(order.uuid),
        receipt_description=order.get_receipt_description(),
    )
    handle_placed_order.delay(order_uuid=unicode(order.uuid))
    return Response(status=204)
