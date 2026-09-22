from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inspection.models import Inspection
from inspection.rules import judge


# 总表收窄允许使用的栏：参数名 -> 中文栏名
SEARCH_FIELDS = {
    "visibility": "能见度",
    "tide_level": "潮位",
    "lamp_device": "灯器",
}

# 新登记必须填齐的三栏：POST 参数名 -> 中文栏名
REQUIRED_FIELDS = {
    "visibility": "能见度",
    "tide_level": "潮位",
    "lamp_device": "灯器",
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
    field_label = ""
    narrowed = False
    # 收窄在服务端查询里完成：栏名走白名单，片段作为 ORM 查询参数绑定
    if field in SEARCH_FIELDS and keyword:
        field_label = SEARCH_FIELDS[field]
        rows = rows.filter(**{f"{field}__icontains": keyword})
        narrowed = True
    return render(
        request,
        "list.html",
        {
            "rows": rows,
            "can_write": _can_write(request.user),
            "search_fields": SEARCH_FIELDS,
            "selected_field": field,
            "keyword": keyword,
            "field_label": field_label,
            "narrowed": narrowed,
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
        "lamp_device": "",
    }
    if request.method == "POST":
        form.update({k: request.POST.get(k, "").strip() for k in form})
        missing = [
            label for name, label in REQUIRED_FIELDS.items() if not form[name]
        ]
        try:
            measured = float(form["measured_cd"])
            required = float(form["required_cd"])
            bearing = float(form["bearing_error_deg"])
        except ValueError:
            error = "请填编号和三项数值"
        if not error and not form["aid_code"]:
            error = "请填航标编号"
        if not error and missing:
            # 三栏缺任何一栏都停在登记页，不写库
            error = "请填齐能见度、潮位、灯器三栏（缺少：%s）" % "、".join(missing)
        if not error:
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
                lamp_device=form["lamp_device"],
                created_by=request.user.username,
            )
            return redirect("detail", pk=row.pk)
    return render(request, "form.html", {"error": error, "form": form})
