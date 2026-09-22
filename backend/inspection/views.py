from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inspection.models import Inspection
from inspection.rules import judge

# 总表可按这三栏片段收窄；白名单避免把列名直接交给 ORM。
FILTER_FIELDS = {
    "visibility": "能见度",
    "tide_level": "潮位",
    "lantern": "灯器",
}


def _can_write(user) -> bool:
    return user.groups.filter(name="inspector").exists()


def health(_request):
    from django.http import JsonResponse

    return JsonResponse({"status": "ok", "service": "nav-aid-inspection"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    from django.contrib.auth import authenticate, login

    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is None:
            error = "用户名或密码错误"
        else:
            login(request, user)
            return redirect("list")
    return render(request, "login.html", {"error": error})


def logout_view(request):
    from django.contrib.auth import logout

    logout(request)
    return redirect("login")


@login_required
def list_view(request):
    rows = Inspection.objects.all()
    field = request.GET.get("field", "")
    keyword = request.GET.get("q", "").strip()
    # 收窄完全在服务端查询里完成：栏位走白名单，关键词走 icontains。
    if field in FILTER_FIELDS and keyword:
        rows = rows.filter(**{f"{field}__icontains": keyword})
    return render(
        request,
        "list.html",
        {
            "rows": rows,
            "can_write": _can_write(request.user),
            "filter_fields": FILTER_FIELDS,
            "active_field": field if field in FILTER_FIELDS else "",
            "active_keyword": keyword if field in FILTER_FIELDS else "",
        },
    )


@login_required
def detail_view(request, pk):
    row = get_object_or_404(Inspection, pk=pk)
    return render(request, "detail.html", {"row": row})


@login_required
@require_http_methods(["GET", "POST"])
def create_view(request):
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可登记灯光巡检")
    error = ""
    form = {
        "aid_code": "",
        "measured_cd": "",
        "required_cd": "1200",
        "bearing_error_deg": "0",
        "visibility": "",
        "tide_level": "",
        "lantern": "",
    }
    if request.method == "POST":
        form.update({k: request.POST.get(k, "").strip() for k in form})
        try:
            measured = float(form["measured_cd"])
            required = float(form["required_cd"])
            bearing = float(form["bearing_error_deg"])
        except ValueError:
            error = "请填三项数值"
        else:
            if not form["aid_code"]:
                error = "请填航标编号"
            # 能见度、潮位、灯器三栏必须单独填齐，缺任何一栏都停在登记页，不入库。
            elif not all((form["visibility"], form["tide_level"], form["lantern"])):
                error = "请填齐能见度、潮位、灯器三栏"
            else:
                verdict, note = judge(measured, required, bearing)
                row = Inspection.objects.create(
                    aid_code=form["aid_code"],
                    measured_cd=measured,
                    required_cd=required,
                    bearing_error_deg=bearing,
                    verdict=verdict,
                    note=note,
                    visibility=form["visibility"],
                    tide_level=form["tide_level"],
                    lantern=form["lantern"],
                    created_by=request.user.username,
                )
                return redirect("detail", pk=row.pk)
    return render(request, "form.html", {"error": error, "form": form})
