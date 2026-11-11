local M = {}
-- Chapter.csv: 11800 is before Roche; 11805 follows his Chapter 11 fight.
-- Cleared saves have already defeated this mandatory boss once.
function M.unlocked(chapter_progress, chapter_select_released)
    if type(chapter_progress) ~= 'number' or chapter_progress < 0 or chapter_progress % 1 ~= 0
       or type(chapter_select_released) ~= 'boolean' then
        return nil, 'completion_state_unobserved'
    end
    return chapter_progress >= 11805 or chapter_select_released
end
function M.policy(chapter_progress, chapter_select_released, invitation_count, discovered)
    local earned,reason=M.unlocked(chapter_progress,chapter_select_released)
    if earned==nil then return nil,reason end
    if type(invitation_count)~='number' or invitation_count<0 or invitation_count%1~=0 or type(discovered)~='boolean' then
        return nil,'invitation_or_discovery_unobserved'
    end
    local chapter4=chapter_progress>=4000 and chapter_progress<5000
    local late=chapter_progress>=12000
    local invitation=invitation_count>0
    return {roche_defeated=earned,chapter4=chapter4,chapter12_plus=late,
        invitation_owned=invitation,discovered=discovered,
        guard_enabled=late and invitation,access_enabled=late and discovered,
        board_enabled=late and discovered,exit_enabled=late,
        -- Owner 2026-11-10: a save past Roche's Chapter 11 fight gets the Invitation
        -- automatically (the resident flow grants it); Chapter 4's Roche never gives it.
        grant_invitation=chapter_progress>=11805 and not invitation}
end
return M
