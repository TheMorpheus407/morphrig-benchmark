#include "MorphRig.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SSlider.h"
#include "Styling/CoreStyle.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "HAL/PlatformMisc.h"

static FSlateFontInfo Font(int32 Size) {return FCoreStyle::GetDefaultFontStyle("Regular",Size);}
static TSharedRef<STextBlock> Label(const FString& Text,int Size=11,FLinearColor Color=FLinearColor(.78,.84,.88),bool Wrap=true) {
    return SNew(STextBlock).Text(FText::FromString(Text)).Font(Font(Size)).ColorAndOpacity(Color).AutoWrapText(Wrap);
}
void AMorphShowroom::BuildUI() {
    auto ActionButton=[&](const FString& Text,TFunction<void()> Callback) -> TSharedRef<SWidget> {
        return SNew(SButton).ContentPadding(FMargin(8,5)).ButtonColorAndOpacity(FLinearColor(.12,.18,.23,.95))
            .OnClicked_Lambda([Callback]() {Callback();return FReply::Handled();})[Label(Text,11,FLinearColor(.78,.84,.88),false)];
    };
    auto Actions=SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3,3)).Visibility_Lambda([this](){return CameraMode==4?EVisibility::Collapsed:EVisibility::Visible;});
    auto Add=[&](FString Name,FString Id) {Actions->AddSlot()[ActionButton(Name,[this,Id]() {Hero->Request(Id);})];};
    Add("Fire [F]","ranged_fire");Add("Burst","ranged_burst");Add("Slash [1]","melee_1");Add("Reverse [2]","melee_2");Add("Finisher [3]","melee_3");
    Add("Reload [R]","reload");Add("Cast [C]","cast_directional");Add("Ground cast","cast_ground");Add("Self cast","cast_self");
    Add("Channel [G]","channel_start");Add("Charge [H]","charge_start");Add("Uplink [U]","uplink_start");Add("Deploy [B]","deploy");
    Actions->AddSlot()[ActionButton("Finish / release [Enter]",[this](){Hero->StopAction(false);})];
    Actions->AddSlot()[ActionButton("Interrupt / cancel [X]",[this](){Hero->StopAction(true);})];
    Add("Hit front","hit_f");Add("Hit back","hit_b");Add("Hit left","hit_l");Add("Hit right","hit_r");
    Add("Stun [K]","stun_start");Add("Sleep","sleep_start");Add("Knockback","knockback");Add("Knock up","knockup_start");
    Add("Down front","knockdown_front");Add("Down back","knockdown_back");Add("Death front [Del]","death_front");Add("Death back","death_back");Add("Respawn","respawn");
    auto Disables=SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3,3)).Visibility_Lambda([this](){return CameraMode==4?EVisibility::Collapsed:EVisibility::Visible;});
    for(FString State:{"none","root","silence","disarm","fear","charm","taunt","stasis"})Disables->AddSlot()[ActionButton(State,[this,State]() {SetDisable(State);})];
    auto Views=SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3,3));
    TArray<FString> ViewNames={"3/4 [V]","Front","Side","Top-down","Face"};
    for(int32 I=0;I<ViewNames.Num();I++)Views->AddSlot()[ActionButton(ViewNames[I],[this,I](){SetCamera(I);})];
    Views->AddSlot()[ActionButton("Team / icon [T]",[this](){Hero->SetTeam(!Hero->TeamB);})];
    Views->AddSlot()[ActionButton("LOD [L]",[this](){SetLOD((LOD+1)%4);})];
    Views->AddSlot()[ActionButton("Skeleton [O]",[this](){Hero->ShowBones=!Hero->ShowBones;})];
    Views->AddSlot()[ActionButton("Normals",[this](){ShowNormals=!ShowNormals;ApplyMaterialMode();})];
    Views->AddSlot()[ActionButton("1 / 10 actors [N]",[this](){ToggleCount();})];
    Views->AddSlot()[ActionButton("Move targets",[this](){MovableTargets=!MovableTargets;})];
    Views->AddSlot()[ActionButton("Wounded [I]",[this](){Hero->Wounded=!Hero->Wounded;})];
    auto Utilities=SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3,3));
    Utilities->AddSlot()[ActionButton("Reset [Backspace]",[this](){Hero->ResetOperative();Demo=false;})];
    Utilities->AddSlot()[ActionButton("Speech",[this](){SetCamera(4);SelectClip("dialogue");})];
    Utilities->AddSlot()[ActionButton("Deterministic demo [F9]",[this](){StartDemo();})];
    Utilities->AddSlot()[ActionButton("Pause [P]",[this](){Hero->Paused=!Hero->Paused;})];
    Utilities->AddSlot()[ActionButton("Save logs",[this](){SaveLogs();})];
    auto Presets=SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(3,3));
    for(FString P:{"neutral","joy","anger","concern","surprise","pain","focus"})Presets->AddSlot()[ActionButton(P,[this,P](){SetFacePreset(P);})];
    SAssignNew(FaceList,SVerticalBox);
    for(const FString& Name:MorphNames)FaceList->AddSlot().AutoHeight().Padding(0,3)[
        SNew(SVerticalBox)+SVerticalBox::Slot().AutoHeight()[Label(Name,10)]+
        SVerticalBox::Slot().AutoHeight()[SNew(SSlider).MinValue(Name.StartsWith("eye_")?-1.f:0.f).MaxValue(1.f).Value_Lambda([this,Name](){return Hero->FaceControls.FindRef(Name);})
            .OnValueChanged_Lambda([this,Name](float V){Hero->FaceControls.FindOrAdd(Name)=V;})]
    ];
    auto Left=SNew(SVerticalBox)
    +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,4)[Label("M O R P H R I G",22,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,16)[Label("OPERATIVE  /  MOTION LABORATORY",10)]
    +SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text_Lambda([this](){return FText::FromString(Status());}).Font(Font(11)).ColorAndOpacity(FLinearColor(.92,.95,.97))]
    +SVerticalBox::Slot().AutoHeight().Padding(0,12,0,6)[Label("INSPECTION",11,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight()[Views]
    +SVerticalBox::Slot().AutoHeight().Padding(0,12,0,6)[Label("96 AUTHORED CLIPS  /  SEARCH & PLAY",11,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight()[SNew(SEditableTextBox).HintText(FText::FromString("Search: walk, death, aim, dialogue...")).OnTextChanged_Lambda([this](const FText& T){Filter=T.ToString();RebuildBrowser();})]
    +SVerticalBox::Slot().FillHeight(1).Padding(0,6)[SAssignNew(BrowserList,SScrollBox)]
    +SVerticalBox::Slot().AutoHeight().Padding(0,7)[Label("ACTION RATE  0.5x - 1.5x",10)]
    +SVerticalBox::Slot().AutoHeight()[SNew(SSlider).MinValue(.5).MaxValue(1.5).Value_Lambda([this](){return Hero->ActionRate;}).OnValueChanged_Lambda([this](float V){if(Hero->ActionId!="dialogue")Hero->ActionRate=V;})]
    +SVerticalBox::Slot().AutoHeight().Padding(0,9,0,0)[Utilities];
    auto Right=SNew(SVerticalBox)
    +SVerticalBox::Slot().AutoHeight()[Label("LIVE CONTROL",13,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight().Padding(0,8)[Label("WASD move | Shift run | Ctrl sprint\nQ / E face | Right mouse aim\nSpace jump | Z dash | J blink\nV camera | Tab panels | Esc quit",11)]
    +SVerticalBox::Slot().AutoHeight().Padding(0,3,0,7)[Label("Aim weight",10)]
    +SVerticalBox::Slot().AutoHeight()[SNew(SSlider).Value_Lambda([this](){return Hero->AimWeight;}).OnValueChanged_Lambda([this](float V){Hero->AimWeight=V;})]
    +SVerticalBox::Slot().AutoHeight().Padding(0,5)[Label("Yaw -60 / +60",10)]
    +SVerticalBox::Slot().AutoHeight()[SNew(SSlider).MinValue(-60).MaxValue(60).Value_Lambda([this](){return Hero->AimYaw;}).OnValueChanged_Lambda([this](float V){Hero->AimYaw=V;Hero->AimWeight=1;})]
    +SVerticalBox::Slot().AutoHeight().Padding(0,5)[Label("Pitch -35 / +35",10)]
    +SVerticalBox::Slot().AutoHeight()[SNew(SSlider).MinValue(-35).MaxValue(35).Value_Lambda([this](){return Hero->AimPitch;}).OnValueChanged_Lambda([this](float V){Hero->AimPitch=V;Hero->AimWeight=1;})]
    +SVerticalBox::Slot().AutoHeight().Padding(0,10)[Actions]
    +SVerticalBox::Slot().AutoHeight()[Label("MODIFIERS",11,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight().Padding(0,5)[Disables]
    +SVerticalBox::Slot().AutoHeight().Padding(0,8)[Label("FACE  /  INDEPENDENT CONTROLS",11,FLinearColor(.25,.92,.89))]
    +SVerticalBox::Slot().AutoHeight()[Presets]
    +SVerticalBox::Slot().AutoHeight().Padding(0,8)[FaceList.ToSharedRef()];
    Panel=SNew(SOverlay)
    +SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Fill).Padding(18,18,0,18)[SNew(SBox).WidthOverride(310)[SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.014,.025,.037,.94)).Padding(18)[Left]]]
    +SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Fill).Padding(0,18,18,18)[SNew(SBox).WidthOverride(322)[SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.014,.025,.037,.94)).Padding(18)[SNew(SScrollBox)+SScrollBox::Slot()[Right]]]]
    +SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(345,0,355,18)[SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0,0,0,.6)).Padding(12)[SNew(STextBlock).Text_Lambda([this](){return FText::FromString(LastTrace);}).ToolTipText_Lambda([this](){return FText::FromString(LastTrace);}).Font(Font(10)).ColorAndOpacity(FLinearColor(.7,.9,.9)).AutoWrapText(false).OverflowPolicy(ETextOverflowPolicy::Ellipsis)]];
    if(GEngine && GEngine->GameViewport)GEngine->GameViewport->AddViewportWidgetContent(Panel.ToSharedRef());
    RebuildBrowser();
}
void AMorphShowroom::RebuildBrowser() {
    if(!BrowserList)return;BrowserList->ClearChildren();
    for(const FString& Id:ClipOrder) {
        if(!Filter.IsEmpty() && !Id.Contains(Filter,ESearchCase::IgnoreCase))continue;
        const auto& C=Clips[Id];
        FString Text=FString::Printf(TEXT("%s  |  %.2fs %s"),*Id,C.Duration,C.Loop?TEXT("loop"):TEXT(""));
        BrowserList->AddSlot().Padding(0,1)[SNew(SButton).ContentPadding(FMargin(7,5)).ButtonColorAndOpacity(FLinearColor(.10,.15,.20,.9)).OnClicked_Lambda([this,Id](){SelectClip(Id);return FReply::Handled();})[Label(Text,10,FLinearColor(.78,.84,.88),false)]];
    }
}
AMorphController::AMorphController() { bShowMouseCursor=true;bEnableClickEvents=true; }
void AMorphController::SetupInputComponent() {Super::SetupInputComponent();}
void AMorphController::KeyAction(FKey Key) {
    if(!Room || !Room->Hero)return;auto* A=Room->Hero;
    if(Key==EKeys::Escape){Room->SaveLogs();FPlatformMisc::RequestExit(false);return;}
    if(Key==EKeys::Tab){Room->UIVisible=!Room->UIVisible;Room->Panel->SetVisibility(Room->UIVisible?EVisibility::Visible:EVisibility::Collapsed);return;}
    if(Key==EKeys::V)Room->SetCamera((Room->CameraMode+1)%5);
    if(Key==EKeys::T)A->SetTeam(!A->TeamB);
    if(Key==EKeys::L)Room->SetLOD((Room->LOD+1)%4);
    if(Key==EKeys::O)A->ShowBones=!A->ShowBones;
    if(Key==EKeys::N)Room->ToggleCount();
    if(Key==EKeys::P)A->Paused=!A->Paused;
    if(Key==EKeys::I)A->Wounded=!A->Wounded;
    if(Key==EKeys::Q && A->GetVelocity().Size2D()<10)A->Request("turn_l90");
    if(Key==EKeys::E && A->GetVelocity().Size2D()<10)A->Request("turn_r90");
    if(Key==EKeys::BackSpace){A->ResetOperative();Room->Demo=false;}
    if(Key==EKeys::F9)Room->StartDemo();
    if(Key==EKeys::Enter)A->StopAction(false);
    if(Key==EKeys::X)A->StopAction(true);
    TMap<FKey,FString> Requests={{EKeys::F,"ranged_fire"},{EKeys::R,"reload"},{EKeys::C,"cast_directional"},{EKeys::G,"channel_start"},{EKeys::H,"charge_start"},{EKeys::U,"uplink_start"},{EKeys::B,"deploy"},{EKeys::K,"stun_start"},{EKeys::Delete,"death_front"},{EKeys::SpaceBar,"jump_start"},{EKeys::Z,"dash_f"},{EKeys::J,"blink_out"},{EKeys::One,"melee_1"},{EKeys::Two,"melee_2"},{EKeys::Three,"melee_3"}};
    if(Requests.Contains(Key))A->Request(Requests[Key]);
}
void AMorphController::PlayerTick(float Dt) {
    Super::PlayerTick(Dt);if(!Room || !Room->Hero)return;auto* A=Room->Hero;
    auto Focus=FSlateApplication::Get().GetKeyboardFocusedWidget();
    bool Typing=Focus.IsValid() && Focus->GetTypeAsString().Contains("EditableText");
    if(Typing)return;
    const TArray<FKey> Keys={EKeys::Escape,EKeys::Tab,EKeys::V,EKeys::T,EKeys::L,EKeys::O,EKeys::N,EKeys::P,EKeys::I,EKeys::Q,EKeys::E,EKeys::BackSpace,EKeys::F9,EKeys::Enter,EKeys::X,EKeys::F,EKeys::R,EKeys::C,EKeys::G,EKeys::H,EKeys::U,EKeys::B,EKeys::K,EKeys::Delete,EKeys::SpaceBar,EKeys::Z,EKeys::J,EKeys::One,EKeys::Two,EKeys::Three};
    for(const FKey& Key:Keys)if(WasInputKeyJustPressed(Key))KeyAction(Key);
    if(A->GetVelocity().Size2D()>10) {
        if(IsInputKeyDown(EKeys::Q))A->Facing-=Dt*110;
        if(IsInputKeyDown(EKeys::E))A->Facing+=Dt*110;
    }
    A->SetActorRotation(FRotator(0,A->Facing,0));
    FVector Input(IsInputKeyDown(EKeys::W)-IsInputKeyDown(EKeys::S),IsInputKeyDown(EKeys::D)-IsInputKeyDown(EKeys::A),0);
    if(A->TranslationAllowed() && !Input.IsNearlyZero()) {
        if(A->BrowserMode) {A->BrowserMode=false;A->ActionId.Empty();A->Paused=false;}
        A->GetCharacterMovement()->MaxWalkSpeed=IsInputKeyDown(EKeys::LeftControl)?650:IsInputKeyDown(EKeys::LeftShift)?400:150;
        if(A->ActionId.IsEmpty() && A->GetVelocity().Size2D()>120 && FVector::DotProduct(Input.GetSafeNormal(),A->GetVelocity().GetSafeNormal2D())<-.7) {
            A->Request(FVector::CrossProduct(A->GetVelocity(),Input).Z<0?"pivot_l180":"pivot_r180");
        }
        A->AddMovementInput(Input.GetSafeNormal());
    }
    FVector Attention(450,0,0);float Nearest=MAX_flt;
    for(auto* Target:Room->Targets) {float D=FVector::DistSquared(Target->GetComponentLocation(),A->GetActorLocation());if(D<Nearest){Nearest=D;Attention=Target->GetComponentLocation();}}
    if(A->TranslationAllowed()) {
        if(A->Disable=="fear")A->AddMovementInput((A->GetActorLocation()-Attention).GetSafeNormal2D());
        if(A->Disable=="charm" && Nearest>10000)A->AddMovementInput((Attention-A->GetActorLocation()).GetSafeNormal2D());
    }
    if(!A->IsTerminal() && A->Disable=="taunt")A->Facing=(Attention-A->GetActorLocation()).Rotation().Yaw;
    if(IsInputKeyDown(EKeys::RightMouseButton)) {
        FVector Origin,Dir;if(DeprojectMousePositionToWorld(Origin,Dir) && FMath::Abs(Dir.Z)>.001) {
            FVector Hit=Origin+Dir*((100-Origin.Z)/Dir.Z),Delta=Hit-A->GetActorLocation();
            A->AimYaw=FMath::Clamp(FMath::FindDeltaAngleDegrees(A->Facing,Delta.Rotation().Yaw),-60.f,60.f);
            A->AimWeight=FMath::FInterpTo(A->AimWeight,1.f,Dt,8);
        }
    }
}
