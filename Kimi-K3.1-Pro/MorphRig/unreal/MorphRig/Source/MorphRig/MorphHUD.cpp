#include "MorphHUD.h"

#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"
#include "MorphCharacter.h"
#include "MorphGameMode.h"
#include "MorphRoom.h"

void UMorphHUD::SetOperative(AMorphCharacter* InOperative)
{
    Operative = InOperative;
    if (ClipGrid.IsValid()) RebuildClipButtons(ClipFilter);
}

void UMorphHUD::SetCapturePresentation()
{
    bCapturePresentation = true;
    RemoveFromParent();
    AddToViewport();
}

void UMorphHUD::TogglePanel()
{
    bPanelVisible = !bPanelVisible;
    if (PanelRoot.IsValid()) PanelRoot->SetVisibility(bPanelVisible ? EVisibility::Visible : EVisibility::Collapsed);
    if (APlayerController* Controller = GetOwningPlayer())
    {
        Controller->bShowMouseCursor = bPanelVisible;
        if (bPanelVisible) Controller->SetInputMode(FInputModeGameAndUI());
        else Controller->SetInputMode(FInputModeGameOnly());
    }
}

TSharedRef<SWidget> UMorphHUD::Button(const FString& Label, TFunction<void()> Action)
{
    return SNew(SButton)
        .Text(FText::FromString(Label))
        .OnClicked_Lambda([Action = MoveTemp(Action)]()
        {
            Action();
            return FReply::Handled();
        });
}

TSharedRef<SWidget> UMorphHUD::Slider(const FString& Label, const float Minimum, const float Maximum, const float Initial, TFunction<void(float)> Action)
{
    return SNew(SBox).HeightOverride(30)
    [
        SNew(SHorizontalBox)
        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 6, 0)
        [ SNew(STextBlock).Text(FText::FromString(Label)) ]
        + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
        [
            SNew(SSlider).MinValue(0.0f).MaxValue(1.0f).Value((Initial - Minimum) / (Maximum - Minimum))
            .OnValueChanged_Lambda([Action = MoveTemp(Action), Minimum, Maximum](float Value)
            {
                Action(FMath::Lerp(Minimum, Maximum, Value));
            })
        ]
    ];
}

void UMorphHUD::Section(TSharedRef<SVerticalBox> Parent, const FString& Label)
{
    Parent->AddSlot().AutoHeight().Padding(2, 8, 2, 3)
    [
        SNew(STextBlock)
        .Text(FText::FromString(Label))
        .Font(FCoreStyle::GetDefaultFontStyle("Bold", 14))
        .ColorAndOpacity(FLinearColor(.1f, .85f, 1.0f))
    ];
}

void UMorphHUD::Row(TSharedRef<SVerticalBox> Parent, std::initializer_list<TSharedRef<SWidget>> Widgets)
{
    TSharedRef<SHorizontalBox> Line = SNew(SHorizontalBox);
    for (const TSharedRef<SWidget>& Widget : Widgets)
    {
        Line->AddSlot().AutoWidth().Padding(2)
        [
            SNew(SBox).MinDesiredWidth(62).HeightOverride(28)[ Widget ]
        ];
    }
    Parent->AddSlot().AutoHeight()[ Line ];
}

void UMorphHUD::RebuildClipButtons(const FString& Filter)
{
    if (!ClipGrid.IsValid()) return;
    ClipGrid->ClearChildren();
    for (const FName Id : UMorphAnimInstance::RequiredClipIds())
    {
        if (!Filter.IsEmpty() && !Id.ToString().Contains(Filter, ESearchCase::IgnoreCase)) continue;
        TWeakObjectPtr<AMorphCharacter> Weak = Operative;
        ClipGrid->AddSlot()
        [
            SNew(SBox).WidthOverride(138).HeightOverride(27).Padding(2)
            [
                Button(Id.ToString(), [Weak, Id]() { if (Weak.IsValid()) Weak->RequestClip(Id); })
            ]
        ];
    }
}

TSharedRef<SWidget> UMorphHUD::RebuildWidget()
{
    if (bCapturePresentation)
    {
        return SNew(SOverlay)
            + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Bottom).Padding(22)
            [
                SNew(SBorder).BorderBackgroundColor(FLinearColor(.015f, .025f, .04f, .85f)).Padding(12)
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [ SAssignNew(StatusText, STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 18)) ]
                    + SVerticalBox::Slot().AutoHeight()
                    [ SAssignNew(DetailText, STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 14)) ]
                ]
            ];
    }
    TSharedRef<SVerticalBox> Controls = SNew(SVerticalBox);
    auto C = [this]() -> AMorphCharacter* { return Operative.Get(); };
    auto G = [this]() -> AMorphGameMode* { return Operative.IsValid() ? Operative->GetWorld()->GetAuthGameMode<AMorphGameMode>() : nullptr; };

    Controls->AddSlot().AutoHeight()
    [
        SNew(STextBlock).Text(FText::FromString(TEXT("MORPHRIG / NATIVE OPERATIVE")))
        .Font(FCoreStyle::GetDefaultFontStyle("Bold", 17))
    ];
    Controls->AddSlot().AutoHeight().Padding(1)
    [
        SAssignNew(StatusText, STextBlock).Text(FText::FromString(TEXT("Loading native assets...")))
    ];
    Controls->AddSlot().AutoHeight().Padding(1)
    [
        SAssignNew(DetailText, STextBlock).Text(FText::FromString(TEXT("")))
    ];

    Section(Controls, TEXT("CAMERA / DISPLAY"));
    Row(Controls, {
        Button(TEXT("Third"), [C]() { if (C()) C()->SetCameraMode(EMorphCameraMode::ThirdPerson); }),
        Button(TEXT("Front"), [C]() { if (C()) C()->SetCameraMode(EMorphCameraMode::Front); }),
        Button(TEXT("Side"), [C]() { if (C()) C()->SetCameraMode(EMorphCameraMode::Side); }),
        Button(TEXT("Top"), [C]() { if (C()) C()->SetCameraMode(EMorphCameraMode::TopDown); }),
        Button(TEXT("Face"), [C]() { if (C()) C()->SetCameraMode(EMorphCameraMode::Face); })
    });
    Row(Controls, {
        Button(TEXT("Team cyan I"), [C]() { if (C()) C()->SetTeam(0); }),
        Button(TEXT("Team amber II"), [C]() { if (C()) C()->SetTeam(1); }),
        Button(TEXT("LOD0"), [C]() { if (C()) C()->SetLOD(0); }),
        Button(TEXT("LOD1"), [C]() { if (C()) C()->SetLOD(1); }),
        Button(TEXT("LOD2"), [C]() { if (C()) C()->SetLOD(2); })
    });
    Row(Controls, {
        Button(TEXT("1 instance"), [G]() { if (G()) G()->SetInstanceCount(1); }),
        Button(TEXT("10 instances"), [G]() { if (G()) G()->SetInstanceCount(10); }),
        Button(TEXT("Targets move/stop"), [G]() { if (G() && G()->GetRoom()) G()->GetRoom()->SetTargetsMoving(!G()->GetRoom()->AreTargetsMoving()); }),
        Button(TEXT("Skeleton"), [C]() { if (C()) C()->ToggleSkeletonDebug(); }),
        Button(TEXT("Lit"), [C]() { if (C()) GEngine->Exec(C()->GetWorld(), TEXT("viewmode lit")); }),
        Button(TEXT("Normals"), [C]() { if (C()) GEngine->Exec(C()->GetWorld(), TEXT("viewmode normal")); })
    });

    Section(Controls, TEXT("LOCOMOTION / AIM / RATE"));
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Speed cm/s"), 0, 650, 0, [C](float V) { if (C()) C()->SetLocomotionDrive(V, C()->GetDriveDirection()); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Direction deg"), -180, 180, 0, [C](float V) { if (C()) C()->SetLocomotionDrive(C()->GetDriveSpeed(), V); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Aim yaw"), -60, 60, 0, [C](float V) { if (C()) C()->SetAim(V, C()->GetAimPitch()); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Aim pitch"), -35, 35, 0, [C](float V) { if (C()) C()->SetAim(C()->GetAimYaw(), V); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Playback x"), .5, 1.5, 1, [C](float V) { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetPlaybackRate(V); }) ];
    Row(Controls, {
        Button(TEXT("Stop"), [C]() { if (C()) C()->StopLocomotionDrive(); }),
        Button(TEXT("Turn L90"), [C]() { if (C()) C()->RequestTurn(-90); }),
        Button(TEXT("Turn R90"), [C]() { if (C()) C()->RequestTurn(90); }),
        Button(TEXT("Pivot L"), [C]() { if (C()) C()->RequestTurn(-180); }),
        Button(TEXT("Pivot R"), [C]() { if (C()) C()->RequestTurn(180); })
    });
    Row(Controls, {
        Button(TEXT("Jump"), [C]() { if (C()) C()->RequestJump(); }),
        Button(TEXT("Dash F"), [C]() { if (C()) C()->RequestDash(TEXT("f")); }),
        Button(TEXT("Dash B"), [C]() { if (C()) C()->RequestDash(TEXT("b")); }),
        Button(TEXT("Dash L"), [C]() { if (C()) C()->RequestDash(TEXT("l")); }),
        Button(TEXT("Dash R"), [C]() { if (C()) C()->RequestDash(TEXT("r")); }),
        Button(TEXT("Blink"), [C]() { if (C()) C()->RequestBlink(); })
    });

    Section(Controls, TEXT("ACTIONS / SUSTAINED STATES"));
    Row(Controls, {
        Button(TEXT("Melee 1"), [C]() { if (C()) C()->RequestMelee(1); }),
        Button(TEXT("Melee 2"), [C]() { if (C()) C()->RequestMelee(2); }),
        Button(TEXT("Melee 3"), [C]() { if (C()) C()->RequestMelee(3); }),
        Button(TEXT("Fire"), [C]() { if (C()) C()->RequestRanged(false); }),
        Button(TEXT("Burst x3"), [C]() { if (C()) C()->RequestRanged(true); }),
        Button(TEXT("Reload"), [C]() { if (C()) C()->RequestReload(); })
    });
    Row(Controls, {
        Button(TEXT("Cast direction"), [C]() { if (C()) C()->RequestCast(TEXT("cast_directional")); }),
        Button(TEXT("Cast ground"), [C]() { if (C()) C()->RequestCast(TEXT("cast_ground")); }),
        Button(TEXT("Cast self"), [C]() { if (C()) C()->RequestCast(TEXT("cast_self")); }),
        Button(TEXT("Deploy"), [C]() { if (C()) C()->RequestDeploy(); })
    });
    Row(Controls, {
        Button(TEXT("Channel start"), [C]() { if (C()) C()->StartChannel(); }),
        Button(TEXT("Channel end"), [C]() { if (C()) C()->FinishChannel(); }),
        Button(TEXT("Channel interrupt"), [C]() { if (C()) C()->InterruptChannel(); })
    });
    Row(Controls, {
        Button(TEXT("Charge start"), [C]() { if (C()) C()->StartCharge(); }),
        Button(TEXT("Charge release"), [C]() { if (C()) C()->ReleaseCharge(); }),
        Button(TEXT("Charge cancel"), [C]() { if (C()) C()->CancelCharge(); })
    });
    Row(Controls, {
        Button(TEXT("Uplink start"), [C]() { if (C()) C()->StartUplink(); }),
        Button(TEXT("Uplink end"), [C]() { if (C()) C()->FinishUplink(); }),
        Button(TEXT("Uplink cancel"), [C]() { if (C()) C()->CancelUplink(); }),
        Button(TEXT("Dialogue + audio"), [C]() { if (C()) C()->PlayDialogue(); })
    });

    Section(Controls, TEXT("HITS / DISABLES / PRIORITIES"));
    Row(Controls, {
        Button(TEXT("Hit F"), [C]() { if (C()) C()->ApplyHit(TEXT("f")); }),
        Button(TEXT("Hit B"), [C]() { if (C()) C()->ApplyHit(TEXT("b")); }),
        Button(TEXT("Hit L"), [C]() { if (C()) C()->ApplyHit(TEXT("l")); }),
        Button(TEXT("Hit R"), [C]() { if (C()) C()->ApplyHit(TEXT("r")); })
    });
    Row(Controls, {
        Button(TEXT("Root toggle"), [C]() { if (C()) C()->SetRooted(!C()->IsRooted()); }),
        Button(TEXT("Silence toggle"), [C]() { if (C()) C()->SetSilenced(!C()->IsSilenced()); }),
        Button(TEXT("Disarm toggle"), [C]() { if (C()) C()->SetDisarmed(!C()->IsDisarmed()); }),
        Button(TEXT("Stasis toggle"), [C]() { if (C()) C()->SetStasis(!C()->IsStasis()); }),
        Button(TEXT("Wounded toggle"), [C]() { if (C()) C()->SetWounded(!C()->IsWounded()); })
    });
    Row(Controls, {
        Button(TEXT("Stun"), [C]() { if (C()) C()->StartStun(); }),
        Button(TEXT("Stun end"), [C]() { if (C()) C()->EndStun(); }),
        Button(TEXT("Sleep"), [C]() { if (C()) C()->StartSleep(); }),
        Button(TEXT("Wake"), [C]() { if (C()) C()->EndSleep(); }),
        Button(TEXT("Knockup"), [C]() { if (C()) C()->Knockup(); }),
        Button(TEXT("Knockback"), [C]() { if (C()) C()->Knockback(); })
    });
    Row(Controls, {
        Button(TEXT("Down front"), [C]() { if (C()) C()->Knockdown(true); }),
        Button(TEXT("Down back"), [C]() { if (C()) C()->Knockdown(false); }),
        Button(TEXT("Get up"), [C]() { if (C()) C()->GetUp(); }),
        Button(TEXT("Death front"), [C]() { if (C()) C()->Die(true); }),
        Button(TEXT("Death back"), [C]() { if (C()) C()->Die(false); }),
        Button(TEXT("Respawn"), [C]() { if (C()) C()->Respawn(); }),
        Button(TEXT("RESET"), [C]() { if (C()) C()->ResetShowcase(); })
    });

    Section(Controls, TEXT("FACE / EYES / VISEMES"));
    Row(Controls, {
        Button(TEXT("Neutral"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("neutral")); }),
        Button(TEXT("Joy"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("joy")); }),
        Button(TEXT("Anger"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("anger")); }),
        Button(TEXT("Concern"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("concern")); }),
        Button(TEXT("Surprise"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("surprise")); }),
        Button(TEXT("Pain"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("pain")); }),
        Button(TEXT("Focus"), [C]() { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFacePreset(TEXT("focus")); })
    });
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Eye L yaw"), -25, 25, 0, [C](float V) { if (C()) C()->SetEyeLook(V, C()->GetEyeLeftPitch(), C()->GetEyeRightYaw(), C()->GetEyeRightPitch()); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Eye L pitch"), -18, 18, 0, [C](float V) { if (C()) C()->SetEyeLook(C()->GetEyeLeftYaw(), V, C()->GetEyeRightYaw(), C()->GetEyeRightPitch()); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Eye R yaw"), -25, 25, 0, [C](float V) { if (C()) C()->SetEyeLook(C()->GetEyeLeftYaw(), C()->GetEyeLeftPitch(), V, C()->GetEyeRightPitch()); }) ];
    Controls->AddSlot().AutoHeight()[ Slider(TEXT("Eye R pitch"), -18, 18, 0, [C](float V) { if (C()) C()->SetEyeLook(C()->GetEyeLeftYaw(), C()->GetEyeLeftPitch(), C()->GetEyeRightYaw(), V); }) ];
    for (const FName Morph : UMorphAnimInstance::FacialMorphNames())
    {
        Controls->AddSlot().AutoHeight()[ Slider(Morph.ToString(), 0, 1, 0, [C, Morph](float V) { if (C() && C()->GetMorphAnim()) C()->GetMorphAnim()->SetFaceValue(Morph, V); }) ];
    }

    Section(Controls, TEXT("96-CLIP SEARCH / DIRECT SAMPLING"));
    Controls->AddSlot().AutoHeight()
    [
        SNew(SEditableTextBox).HintText(FText::FromString(TEXT("Search all 96 imported clips...")))
        .OnTextChanged_Lambda([this](const FText& Text)
        {
            ClipFilter = Text.ToString();
            RebuildClipButtons(ClipFilter);
        })
    ];
    Controls->AddSlot().AutoHeight()[ SAssignNew(ClipGrid, SWrapBox).PreferredSize(450) ];

    Section(Controls, TEXT("IN-APP KEY GUIDE"));
    Controls->AddSlot().AutoHeight()
    [
        SNew(STextBlock).AutoWrapText(true).Text(FText::FromString(
            TEXT("F1 panel  |  WASD move  |  mouse camera  |  Shift sprint  |  Space jump\n")
            TEXT("F dash  |  B blink  |  LMB fire  |  R burst  |  M melee  |  Q/E turn\n")
            TEXT("C channel (release ends)  |  X interrupt  |  V charge (release fires)  |  Z cancel\n")
            TEXT("Tab camera  |  Y dialogue  |  T team  |  K respawn  |  Backspace reset\n")
            TEXT("All other states, face sliders, LODs and instance counts are above.")))
    ];

    PanelRoot = SNew(SBorder)
        .BorderBackgroundColor(FLinearColor(.015f, .025f, .04f, .92f))
        .Padding(8)
        [
            SNew(SBox).WidthOverride(480).MaxDesiredHeight(940)
            [
                SNew(SScrollBox)
                + SScrollBox::Slot()[ Controls ]
            ]
        ];
    return SNew(SOverlay)
        + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(12)
        [ PanelRoot.ToSharedRef() ];
}

void UMorphHUD::NativeTick(const FGeometry& MyGeometry, const float InDeltaTime)
{
    Super::NativeTick(MyGeometry, InDeltaTime);
    RefreshRemaining -= InDeltaTime;
    if (RefreshRemaining > 0.0f || !Operative.IsValid()) return;
    RefreshRemaining = bCapturePresentation ? 0.0f : .1f;
    AMorphCharacter* Character = Operative.Get();
    const UMorphAnimInstance* Anim = Character->GetMorphAnim();
    if (!Anim) return;
    const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
    if (StatusText.IsValid())
    {
        StatusText->SetText(FText::FromString(FString::Printf(
            TEXT("%s | %s | team %s LOD%d | %d/96 clips%s"),
            *Character->GetStateName(), *Character->GetCameraModeName(), Character->GetTeam() == 0 ? TEXT("I") : TEXT("II"),
            Character->GetLOD(), Snapshot.LoadedClipCount, Anim->IsManifestLoaded() ? TEXT(" + manifest") : TEXT(" (manifest pending)"))));
    }
    if (DetailText.IsValid())
    {
        DetailText->SetText(FText::FromString(FString::Printf(
            TEXT("main %s %.3f/%.3fs x%.2f blend %.2f\nupper %s %.3fs | additive %s\nevent %s | props %s | aim %.0f/%.0f | IK %s | audio %s\nflags:%s%s%s%s%s%s"),
            *Snapshot.MainClip.ToString(), Snapshot.MainTime, Snapshot.MainDuration, Snapshot.MainRate, Snapshot.MainBlend,
            *Snapshot.UpperClip.ToString(), Snapshot.UpperTime, *Snapshot.AdditiveClip.ToString(),
            *Snapshot.LastEvent.ToString(), *Character->GetPropState(), Character->GetAimYaw(), Character->GetAimPitch(),
            Snapshot.bGroundIK ? TEXT("on") : TEXT("off"), Character->IsDialoguePlaying() ? TEXT("playing") : TEXT("stopped"),
            Character->IsRooted() ? TEXT(" root") : TEXT(""), Character->IsSilenced() ? TEXT(" silence") : TEXT(""),
            Character->IsDisarmed() ? TEXT(" disarm") : TEXT(""), Character->IsStasis() ? TEXT(" stasis") : TEXT(""),
            Character->IsWounded() ? TEXT(" wounded") : TEXT(""), Character->IsDead() ? TEXT(" dead") : TEXT(""))));
    }
}
